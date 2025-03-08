import os
import sys
import time
import asyncio
import json
import traceback
from typing import Dict, List, Optional
from datetime import datetime, timezone
from loguru import logger
import redis
from redis import Redis

from util import ArchiverRedisLock

class RelayCoordinator:
    """Manages relay assignments and distribution across collectors"""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.redis_relay_lock_key = "dvmdash_relay_distribution_lock"
        self.distribution_interval = int(os.getenv("RELAY_DISTRIBUTION_INTERVAL_SECONDS", 30))
        self.last_distribution = 0
        self.collector_timeout = int(os.getenv("COLLECTOR_TIMEOUT_SECONDS", 300))  # 5 minutes
        
    async def get_all_relays(self) -> Dict[str, Dict]:
        """Get all configured relays and their settings"""
        relays = self.redis.get('dvmdash:settings:relays')
        return json.loads(relays) if relays else {}
    
    async def get_active_collectors(self) -> List[str]:
        """Get list of active collectors based on heartbeat"""
        collectors = list(self.redis.smembers('dvmdash:collectors:active'))
        active_collectors = []
        
        current_time = int(time.time())
        active_threshold = current_time - self.collector_timeout
        
        for collector_id in collectors:
            heartbeat = self.redis.get(f'dvmdash:collector:{collector_id}:heartbeat')
            # Include collectors without heartbeats (they might be starting up)
            # Only remove collectors with heartbeats older than timeout
            if not heartbeat or int(heartbeat) >= active_threshold:
                active_collectors.append(collector_id)
        
        return active_collectors
    
    async def should_redistribute_relays(self) -> bool:
        """Check if relays should be redistributed"""
        # Check if enough time has passed since last distribution
        if time.time() - self.last_distribution < self.distribution_interval:
            return False
            
        # Check if there's an explicit distribution request
        distribution_requested = self.redis.get('dvmdash:settings:distribution_requested')
        if distribution_requested:
            logger.info("Explicit relay distribution request found")
            return True
            
        # Check if there's a pending config change
        last_change = self.redis.get('dvmdash:settings:last_change')
        if last_change and int(last_change) > self.last_distribution:
            logger.info("Config change detected since last distribution")
            return True
            
        # Check if there are outdated collectors
        outdated = await self.get_outdated_collectors()
        if outdated:
            logger.info(f"Found {len(outdated)} outdated collectors that need relay updates")
            return True
            
        # Check if there are collectors without relay assignments
        collectors = await self.get_active_collectors()
        for collector_id in collectors:
            relays = self.redis.get(f'dvmdash:collector:{collector_id}:relays')
            if not relays or relays == '{}':
                logger.info(f"Collector {collector_id} has no relay assignments")
                return True
                
        return False
    
    async def get_outdated_collectors(self) -> List[str]:
        """Get list of collector IDs that need to be updated"""
        try:
            current_version = self.redis.get('dvmdash:settings:config_version')
            if not current_version:
                return []

            collectors = await self.get_active_collectors()
            outdated = []
            
            for collector_id in collectors:
                # Check if collector is outdated based on config version
                collector_version = self.redis.get(f'dvmdash:collector:{collector_id}:config_version')
                if not collector_version or int(collector_version) != int(current_version):
                    outdated.append(collector_id)
            
            return outdated
        except Exception as e:
            logger.error(f"Error checking outdated collectors: {e}")
            return []
    
    async def distribute_relays(self) -> bool:
        """
        Distribute relays across active collectors.
        Rules:
        1. Maximum 3 relays per collector
        2. Try to distribute high-activity relays evenly
        3. Distribute remaining relays evenly
        """
        try:
            logger.info("Starting relay distribution...")
            
            # Use a lock to prevent multiple coordinators from distributing simultaneously
            with ArchiverRedisLock(
                self.redis,
                self.redis_relay_lock_key,
                expire_seconds=30,
                retry_times=3,
                retry_delay=1.0,
            ) as lock:
                # Get current configuration
                relays_config = await self.get_all_relays()
                logger.info(f"Found {len(relays_config)} relays in configuration")
                
                # If no relays are configured, check if we need to initialize from config
                if not relays_config:
                    logger.warning("No relays found in Redis, checking if we need to initialize from config")
                    # Try to get relays from config:relays (without dvmdash: prefix)
                    config_relays = self.redis.get('config:relays')
                    if config_relays:
                        try:
                            relays_dict = json.loads(config_relays)
                            logger.info(f"Found {len(relays_dict)} relays in config:relays, copying to dvmdash:settings:relays")
                            # Copy to dvmdash:settings:relays
                            self.redis.set('dvmdash:settings:relays', config_relays)
                            relays_config = relays_dict
                        except json.JSONDecodeError:
                            logger.error(f"Error decoding config:relays: {config_relays}")
                
                # If still no relays, create a default configuration
                if not relays_config:
                    logger.warning("No relays found, creating default configuration")
                    default_relays = {
                        "wss://relay.damus.io": {"activity": "normal", "added_at": int(time.time()), "added_by": "system"},
                        "wss://relay.primal.net": {"activity": "normal", "added_at": int(time.time()), "added_by": "system"},
                        "wss://relay.dvmdash.live": {"activity": "normal", "added_at": int(time.time()), "added_by": "system"},
                        "wss://relay.f7z.xyz": {"activity": "normal", "added_at": int(time.time()), "added_by": "system"},
                        "wss://relayable.org": {"activity": "normal", "added_at": int(time.time()), "added_by": "system"}
                    }
                    self.redis.set('dvmdash:settings:relays', json.dumps(default_relays))
                    relays_config = default_relays
                    logger.info(f"Created default relay configuration with {len(default_relays)} relays")
                
                collectors = await self.get_active_collectors()
                logger.info(f"Found {len(collectors)} active collectors")
                
                if not collectors:
                    logger.warning("No active collectors found")
                    return False

                # Separate relays by activity level
                high_activity = []
                normal_activity = []
                for relay_url, config in relays_config.items():
                    if config["activity"] == "high":
                        high_activity.append(relay_url)
                    else:
                        normal_activity.append(relay_url)
                
                logger.info(f"Found {len(high_activity)} high-activity relays and {len(normal_activity)} normal relays")

                # Calculate distribution
                assignments = {c: [] for c in collectors}
                max_relays_per_collector = 3  # Maximum number of relays per collector
                
                # First distribute high-activity relays
                collector_index = 0
                for relay in high_activity:
                    while len(assignments[collectors[collector_index]]) >= max_relays_per_collector:
                        collector_index = (collector_index + 1) % len(collectors)
                    assignments[collectors[collector_index]].append(relay)
                    collector_index = (collector_index + 1) % len(collectors)

                # Then distribute normal relays
                collector_index = 0
                for relay in normal_activity:
                    # Skip collectors that already have the maximum number of relays
                    while len(assignments[collectors[collector_index]]) >= max_relays_per_collector:
                        collector_index = (collector_index + 1) % len(collectors)
                        # If we've checked all collectors and they're all at max capacity,
                        # some relays won't be assigned, which is fine
                        if all(len(assignments[c]) >= max_relays_per_collector for c in collectors):
                            logger.info("All collectors at maximum relay capacity, some relays will remain unassigned")
                            break
                    
                    # If all collectors are at max capacity, stop assigning relays
                    if all(len(assignments[c]) >= max_relays_per_collector for c in collectors):
                        logger.info(f"Relay {relay} will remain unassigned")
                        continue
                        
                    assignments[collectors[collector_index]].append(relay)
                    collector_index = (collector_index + 1) % len(collectors)

                # Update Redis with new assignments
                with self.redis.pipeline() as pipe:
                    for collector_id, relays in assignments.items():
                        relay_dict = {r: relays_config[r] for r in relays}
                        relay_json = json.dumps(relay_dict)
                        
                        # Update in dvmdash:collector:{id}:relays
                        pipe.set(
                            f'dvmdash:collector:{collector_id}:relays',
                            relay_json
                        )
                        
                        # Also update in the collectors hash for the admin UI
                        pipe.hset(
                            f'collectors:{collector_id}',
                            'relays',
                            relay_json
                        )
                        
                        # Update collector's config version
                        current_version = self.redis.get('dvmdash:settings:config_version')
                        if current_version:
                            pipe.set(
                                f'dvmdash:collector:{collector_id}:config_version',
                                current_version
                            )
                            pipe.hset(
                                f'collectors:{collector_id}',
                                'config_version',
                                current_version
                            )
                        
                        logger.info(f"Assigned {len(relays)} relays to collector {collector_id}")
                    
                    pipe.execute()
                
                # Clear the distribution request flag if it exists
                self.redis.delete('dvmdash:settings:distribution_requested')
                
                self.last_distribution = time.time()
                logger.info("Relay distribution completed successfully")
                return True

        except Exception as e:
            logger.error(f"Error distributing relays: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def check_collector_health(self) -> None:
        """Check health of collectors and remove stale ones"""
        try:
            collectors = list(self.redis.smembers('dvmdash:collectors:active'))
            current_time = int(time.time())
            stale_threshold = current_time - self.collector_timeout
            
            stale_collectors = []
            for collector_id in collectors:
                heartbeat = self.redis.get(f'dvmdash:collector:{collector_id}:heartbeat')
                if heartbeat and int(heartbeat) < stale_threshold:
                    stale_collectors.append(collector_id)
            
            if stale_collectors:
                logger.info(f"Found {len(stale_collectors)} stale collectors to remove")
                
                with self.redis.pipeline() as pipe:
                    for collector_id in stale_collectors:
                        # Remove from active set
                        pipe.srem('dvmdash:collectors:active', collector_id)
                        
                        # Log the removal
                        logger.info(f"Removing stale collector {collector_id}, last heartbeat: {heartbeat}")
                    
                    pipe.execute()
                
                # Redistribute relays if we removed any collectors
                await self.distribute_relays()
            
        except Exception as e:
            logger.error(f"Error checking collector health: {e}")
            logger.error(traceback.format_exc())

class HistoricalDataCoordinator:
    """Manages loading of historical data (placeholder for future implementation)"""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        
    async def check_historical_data_requests(self) -> None:
        """Check for historical data loading requests"""
        # This is a placeholder for future implementation
        pass

class CoordinatorManager:
    """Main coordinator class that manages various coordination tasks"""
    
    def __init__(self, redis_client: Redis, metrics_pool):
        self.redis = redis_client
        self.metrics_pool = metrics_pool
        self.relay_coordinator = RelayCoordinator(redis_client)
        self.historical_coordinator = HistoricalDataCoordinator(redis_client)
        
        # Timing controls
        self.last_health_check = 0
        self.health_check_interval = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", 60))
        self.last_relay_check = 0
        self.relay_check_interval = int(os.getenv("RELAY_CHECK_INTERVAL_SECONDS", 5))
        
    async def process_forever(self):
        """Main processing loop for the coordinator"""
        consecutive_errors = 0
        last_health_log = time.time()
        
        while True:
            try:
                current_time = time.time()
                
                # Check for relay distribution needs
                if current_time - self.last_relay_check >= self.relay_check_interval:
                    if await self.relay_coordinator.should_redistribute_relays():
                        await self.relay_coordinator.distribute_relays()
                    self.last_relay_check = current_time
                
                # Check collector health
                if current_time - self.last_health_check >= self.health_check_interval:
                    await self.relay_coordinator.check_collector_health()
                    self.last_health_check = current_time
                
                # Check for historical data requests (future implementation)
                await self.historical_coordinator.check_historical_data_requests()
                
                # Health check logging
                if current_time - last_health_log >= 60:
                    logger.info(f"Health check - Coordinator running normally")
                    last_health_log = current_time
                
                # Small sleep to prevent tight loop
                await asyncio.sleep(1)
                consecutive_errors = 0
                
            except Exception as e:
                logger.error(f"Error in coordinator processing loop: {e}")
                logger.error(traceback.format_exc())
                consecutive_errors += 1
                
                if consecutive_errors >= 10:
                    logger.critical("Too many consecutive errors (10+), shutting down for safety...")
                    return
                
                # Exponential backoff on errors
                await asyncio.sleep(min(30, 2**consecutive_errors))
