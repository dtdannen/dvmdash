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
        self.collector_timeout = int(os.getenv("COLLECTOR_TIMEOUT_SECONDS", 60))  # 1 minute
        
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
        
        # Give new collectors a grace period to send their first heartbeat
        grace_period = 30  # seconds
        
        for collector_id in collectors:
            # Ensure collector_id is a string for Redis key
            collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
            
            # Get collector data from hash
            collector_data = self.redis.hgetall(f'dvmdash:collector:{collector_id_str}')
            
            # Check for heartbeat in collector data (handling byte strings)
            has_heartbeat = False
            heartbeat_value = None
            
            for key in collector_data:
                # Convert byte string keys to regular strings if needed
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                if key_str == 'heartbeat':
                    has_heartbeat = True
                    value = collector_data[key]
                    heartbeat_value = int(value.decode('utf-8') if isinstance(value, bytes) else value)
                    break
            
            if has_heartbeat and heartbeat_value >= active_threshold:
                active_collectors.append(collector_id)
                continue
            
            # For collectors without heartbeats, check if they were recently added
            has_registration = False
            registration_time = None
            
            for key in collector_data:
                # Convert byte string keys to regular strings if needed
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                if key_str == 'registered_at':
                    has_registration = True
                    value = collector_data[key]
                    registration_time = int(value.decode('utf-8') if isinstance(value, bytes) else value)
                    break
            
            if has_registration and current_time - registration_time < grace_period:
                logger.info(f"Including recently registered collector {collector_id_str} in active collectors (no heartbeat yet)")
                active_collectors.append(collector_id)
                continue
            
            # If we don't have registration data, give benefit of doubt for a short grace period
            logger.debug(f"Collector {collector_id_str} has no heartbeat, including in active collectors during grace period")
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
            # Ensure collector_id is a string for Redis key
            collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
            
            relays = self.redis.get(f'dvmdash:collector:{collector_id_str}:relays')
            if not relays or relays == '{}':
                logger.info(f"Collector {collector_id_str} has no relay assignments")
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
                # Ensure collector_id is a string for Redis key
                collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
                
                # Check if collector is outdated based on config version in the hash
                collector_data = self.redis.hgetall(f'dvmdash:collector:{collector_id_str}')
                
                # Check for config_version in collector data (handling byte strings)
                has_config_version = False
                config_version_value = None
                
                for key in collector_data:
                    # Convert byte string keys to regular strings if needed
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    if key_str == 'config_version':
                        has_config_version = True
                        value = collector_data[key]
                        config_version_value = int(value.decode('utf-8') if isinstance(value, bytes) else value)
                        break
                
                if not has_config_version or config_version_value != int(current_version):
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
                        "wss://relay.dvmdash.live": {"activity": "normal", "added_at": int(time.time()), "added_by": "system"}
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
                        # Ensure collector_id is a string
                        collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
                        
                        relay_dict = {r: relays_config[r] for r in relays}
                        relay_json = json.dumps(relay_dict)
                        
                        # Update in dvmdash:collector:{id}:relays
                        pipe.set(
                            f'dvmdash:collector:{collector_id_str}:relays',
                            relay_json
                        )
                        
                        # Update collector's config version in the hash
                        current_version = self.redis.get('dvmdash:settings:config_version')
                        if current_version:
                            pipe.hset(
                                f'dvmdash:collector:{collector_id_str}',
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
                # Ensure collector_id is a string for Redis key
                collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
                
                # Get collector data from hash
                collector_data = self.redis.hgetall(f'dvmdash:collector:{collector_id_str}')
                
                # Consider a collector stale if:
                # 1. It has a heartbeat older than the threshold, OR
                # 2. It has no heartbeat (null) and has been in the system for longer than the timeout
                
                # Check for heartbeat in collector data (handling byte strings)
                has_heartbeat = False
                heartbeat_value = None
                
                for key in collector_data:
                    # Convert byte string keys to regular strings if needed
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    if key_str == 'heartbeat':
                        has_heartbeat = True
                        value = collector_data[key]
                        heartbeat_value = int(value.decode('utf-8') if isinstance(value, bytes) else value)
                        break
                
                if has_heartbeat:
                    if heartbeat_value < stale_threshold:
                        # Case 1: Collector has an old heartbeat
                        logger.info(f"Collector {collector_id_str} has stale heartbeat: {heartbeat_value} < {stale_threshold}")
                        stale_collectors.append(collector_id)
                else:
                    # Case 2: Collector has no heartbeat
                    has_registration = False
                    registration_time = None
                    
                    for key in collector_data:
                        # Convert byte string keys to regular strings if needed
                        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                        if key_str == 'registered_at':
                            has_registration = True
                            value = collector_data[key]
                            registration_time = int(value.decode('utf-8') if isinstance(value, bytes) else value)
                            break
                    
                    if has_registration:
                        # Only mark as stale if it's been registered for longer than the collector timeout
                        if current_time - registration_time > self.collector_timeout:
                            logger.info(f"Collector {collector_id_str} has no heartbeat and was registered {current_time - registration_time}s ago, marking as stale")
                            stale_collectors.append(collector_id)
                        else:
                            logger.info(f"Collector {collector_id_str} has no heartbeat but was recently registered ({current_time - registration_time}s ago), not marking as stale yet")
                    else:
                        # If we can't determine when it was added, be conservative and mark as stale
                        logger.info(f"Collector {collector_id_str} has no heartbeat and no registration time, marking as stale")
                        logger.info(f"collector_data is {collector_data}")
                        stale_collectors.append(collector_id)
            
            if stale_collectors:
                logger.info(f"Found {len(stale_collectors)} stale collectors to remove")
                
                with self.redis.pipeline() as pipe:
                    for collector_id in stale_collectors:
                        # Ensure collector_id is a string for Redis key
                        collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
                        
                        # Remove from active set
                        pipe.srem('dvmdash:collectors:active', collector_id)
                        
                        # Clean up collector keys
                        pipe.delete(f'dvmdash:collector:{collector_id_str}')
                        pipe.delete(f'dvmdash:collector:{collector_id_str}:relays')
                        pipe.delete(f'dvmdash:collector:{collector_id_str}:nsec_key')
                        
                        # Log the removal
                        logger.info(f"Removing stale collector {collector_id_str}")
                    
                    pipe.execute()
                
                # Clean up metrics keys for stale collectors
                await self._cleanup_collector_metrics(stale_collectors)
                
                # Redistribute relays if we removed any collectors
                await self.distribute_relays()
            
        except Exception as e:
            logger.error(f"Error checking collector health: {e}")
            logger.error(traceback.format_exc())
            
    async def _cleanup_collector_metrics(self, stale_collectors: List) -> None:
        """Clean up metrics keys for stale collectors"""
        try:
            for collector_id in stale_collectors:
                # Ensure collector_id is a string for Redis key
                collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
                
                # Find all metrics keys for this collector
                metrics_pattern = f'dvmdash:collector:{collector_id_str}:metrics:*'
                metrics_keys = self.redis.keys(metrics_pattern)
                
                if metrics_keys:
                    logger.info(f"Cleaning up {len(metrics_keys)} metrics keys for stale collector {collector_id_str}")
                    
                    # Delete all metrics keys in batches to avoid blocking Redis
                    batch_size = 100
                    for i in range(0, len(metrics_keys), batch_size):
                        batch = metrics_keys[i:i+batch_size]
                        if batch:
                            self.redis.delete(*batch)
                            logger.debug(f"Deleted batch of {len(batch)} metrics keys for collector {collector_id_str}")
                
                # Also clean up any other collector-related keys that might exist
                alt_metrics_pattern = f'collectors:{collector_id_str}:metrics:*'
                alt_metrics_keys = self.redis.keys(alt_metrics_pattern)
                
                if alt_metrics_keys:
                    logger.info(f"Cleaning up {len(alt_metrics_keys)} alternate metrics keys for stale collector {collector_id_str}")
                    
                    # Delete all alternate metrics keys in batches
                    batch_size = 100
                    for i in range(0, len(alt_metrics_keys), batch_size):
                        batch = alt_metrics_keys[i:i+batch_size]
                        if batch:
                            self.redis.delete(*batch)
                            logger.debug(f"Deleted batch of {len(batch)} alternate metrics keys for collector {collector_id_str}")
                
        except Exception as e:
            logger.error(f"Error cleaning up metrics keys: {e}")
            logger.error(traceback.format_exc())

class HistoricalDataCoordinator:
    """Manages loading of historical data (placeholder for future implementation)"""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        
    async def check_historical_data_requests(self) -> None:
        """Check for historical data loading requests"""
        # This is a placeholder for future implementation
        pass

class EventCollectorCoordinatorManager:
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
        self.last_global_cleanup = 0
        self.global_cleanup_interval = int(os.getenv("GLOBAL_CLEANUP_INTERVAL_SECONDS", 3600))  # Default: 1 hour
        
        # Initialize nsec keys from environment variable
        self._initialize_nsec_keys()
    
    def _initialize_nsec_keys(self):
        """Initialize nsec keys in Redis from environment variable"""
        nsec_keys = os.getenv("DVMDASH_LISTENER_NSECS", "")
        
        if not nsec_keys:
            logger.warning("No DVMDASH_LISTENER_NSECS environment variable set, collectors will generate their own keys")
            return
            
        keys_list = nsec_keys.split(",")
        logger.info(f"Initializing {len(keys_list)} nsec keys from environment variable")
        
        # Only set keys if they don't already exist in Redis
        if not self.redis.exists("dvmdash:settings:nsec_keys"):
            # Store keys in Redis
            for i, key in enumerate(keys_list):
                self.redis.hset("dvmdash:settings:nsec_keys", f"key_{i}", key)
            
            logger.info(f"Stored {len(keys_list)} nsec keys in Redis")
    
    def assign_nsec_key(self, collector_id):
        """Assign an nsec key to a collector"""
        # Check if collector already has a key
        existing_key = self.redis.get(f"dvmdash:collector:{collector_id}:nsec_key")
        if existing_key:
            logger.info(f"Collector {collector_id} already has nsec key assigned")
            return True
            
        # Get all keys
        all_keys = self.redis.hgetall("dvmdash:settings:nsec_keys")
        if not all_keys:
            logger.warning("No nsec keys available in Redis")
            return False
            
        # Get all assigned keys
        assigned_keys = {}
        for c_id in self.redis.smembers("dvmdash:collectors:active"):
            c_id_str = c_id.decode("utf-8") if isinstance(c_id, bytes) else c_id
            key = self.redis.get(f"dvmdash:collector:{c_id_str}:nsec_key")
            if key:
                assigned_keys[c_id_str] = key.decode("utf-8") if isinstance(key, bytes) else key
        
        # Find an unassigned key
        for key_id, key_value in all_keys.items():
            key_str = key_value.decode("utf-8") if isinstance(key_value, bytes) else key_value
            if key_str not in assigned_keys.values():
                # Assign this key to the collector
                self.redis.set(f"dvmdash:collector:{collector_id}:nsec_key", key_str)
                logger.info(f"Assigned nsec key {key_id} to collector {collector_id}")
                return True
        
        # If we get here, all keys are assigned
        error_msg = f"Unable to assign nsec key to collector {collector_id}, all keys are in use"
        logger.error(error_msg)
        self.redis.rpush("dvmdash:errors", error_msg)
        return False
        
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
                        # Distribute relays
                        distribution_success = await self.relay_coordinator.distribute_relays()
                        
                        # If relay distribution was successful, also assign nsec keys
                        if distribution_success:
                            collectors = await self.relay_coordinator.get_active_collectors()
                            for collector_id in collectors:
                                collector_id_str = collector_id.decode("utf-8") if isinstance(collector_id, bytes) else collector_id
                                self.assign_nsec_key(collector_id_str)
                                
                    self.last_relay_check = current_time
                
                # Check collector health
                if current_time - self.last_health_check >= self.health_check_interval:
                    await self.relay_coordinator.check_collector_health()
                    self.last_health_check = current_time
                
                # Perform global cleanup of orphaned Redis keys
                if current_time - self.last_global_cleanup >= self.global_cleanup_interval:
                    await self._perform_global_cleanup()
                    self.last_global_cleanup = current_time
                
                # Check for historical data requests (future implementation)
                await self.historical_coordinator.check_historical_data_requests()
                
                # Health check logging
                if current_time - last_health_log >= 60:
                    logger.info(f"Health check - Coordinator running normally")
                    
                    # Log relay assignments
                    try:
                        collectors = await self.relay_coordinator.get_active_collectors()
                        logger.info(f"Current relay assignments for {len(collectors)} active collectors:")
                        
                        current_time = int(time.time())
                        
                        for collector_id in collectors:
                            # Ensure collector_id is a string for Redis key
                            collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
                            
                            # Get heartbeat information from the hash
                            collector_data = self.redis.hgetall(f'dvmdash:collector:{collector_id_str}')
                            heartbeat_age = "Never"
                            
                            # Check for heartbeat in collector data (handling byte strings)
                            for key in collector_data:
                                # Convert byte string keys to regular strings if needed
                                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                                if key_str == 'heartbeat':
                                    value = collector_data[key]
                                    heartbeat_timestamp = int(value.decode('utf-8') if isinstance(value, bytes) else value)
                                    heartbeat_age = f"{current_time - heartbeat_timestamp} seconds ago"
                                    break
                            
                            # Get relay assignments
                            relays_json = self.redis.get(f'dvmdash:collector:{collector_id_str}:relays')
                            relays = json.loads(relays_json) if relays_json else {}
                            
                            logger.info(f"  Collector {collector_id_str}: {len(relays)} relays assigned, last heartbeat: {heartbeat_age}")
                            for relay_url in relays.keys():
                                logger.info(f"    - {relay_url}")
                    except Exception as e:
                        logger.error(f"Error logging relay assignments: {e}")
                    
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
    
    async def _perform_global_cleanup(self):
        """Perform global cleanup of orphaned Redis keys"""
        try:
            logger.info("Starting global Redis key cleanup")
            
            # Get all active collectors
            active_collectors = await self.relay_coordinator.get_active_collectors()
            active_collector_ids = [
                c.decode('utf-8') if isinstance(c, bytes) else c 
                for c in active_collectors
            ]
            
            # Find all collector-related keys
            collector_metrics_pattern = "dvmdash:collector:*:metrics:*"
            all_metrics_keys = self.redis.keys(collector_metrics_pattern)
            
            if not all_metrics_keys:
                logger.info("No metrics keys found during global cleanup")
                return
                
            logger.info(f"Found {len(all_metrics_keys)} total metrics keys during global cleanup")
            
            # Identify orphaned keys (those belonging to collectors that no longer exist)
            orphaned_keys = []
            for key in all_metrics_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                
                # Extract collector ID from key
                # Format: dvmdash:collector:{collector_id}:metrics:{relay_url}
                parts = key_str.split(':')
                if len(parts) >= 3:
                    collector_id = parts[2]
                    
                    if collector_id not in active_collector_ids:
                        orphaned_keys.append(key)
            
            # Delete orphaned keys in batches
            if orphaned_keys:
                logger.info(f"Found {len(orphaned_keys)} orphaned metrics keys to clean up")
                
                batch_size = 100
                for i in range(0, len(orphaned_keys), batch_size):
                    batch = orphaned_keys[i:i+batch_size]
                    if batch:
                        self.redis.delete(*batch)
                        logger.info(f"Deleted batch of {len(batch)} orphaned metrics keys")
                        
                        # Small sleep to avoid blocking Redis
                        await asyncio.sleep(0.1)
            else:
                logger.info("No orphaned metrics keys found during global cleanup")
            
            # Also check for orphaned alternate metrics keys
            alt_metrics_pattern = "collectors:*:metrics:*"
            alt_metrics_keys = self.redis.keys(alt_metrics_pattern)
            
            if alt_metrics_keys:
                orphaned_alt_keys = []
                for key in alt_metrics_keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    
                    # Extract collector ID from key
                    # Format: collectors:{collector_id}:metrics:{relay_url}
                    parts = key_str.split(':')
                    if len(parts) >= 2:
                        collector_id = parts[1]
                        
                        if collector_id not in active_collector_ids:
                            orphaned_alt_keys.append(key)
                
                # Delete orphaned alternate keys in batches
                if orphaned_alt_keys:
                    logger.info(f"Found {len(orphaned_alt_keys)} orphaned alternate metrics keys to clean up")
                    
                    batch_size = 100
                    for i in range(0, len(orphaned_alt_keys), batch_size):
                        batch = orphaned_alt_keys[i:i+batch_size]
                        if batch:
                            self.redis.delete(*batch)
                            logger.info(f"Deleted batch of {len(batch)} orphaned alternate metrics keys")
                            
                            # Small sleep to avoid blocking Redis
                            await asyncio.sleep(0.1)
                else:
                    logger.info("No orphaned alternate metrics keys found during global cleanup")
            
            logger.info("Global Redis key cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during global Redis key cleanup: {e}")
            logger.error(traceback.format_exc())
