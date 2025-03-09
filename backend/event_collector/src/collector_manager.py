import uuid
import time
import json
import asyncio
import traceback
from typing import Dict, List, Optional
from redis import Redis
import logging

logger = logging.getLogger(__name__)

class CollectorManager:
    """Manages collector registration, heartbeat, and status in Redis"""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.collector_id = str(uuid.uuid4())
        self.heartbeat_interval = 5  # seconds
        self._heartbeat_task = None
        
    async def register(self):
        """Register this collector instance in Redis"""
        current_time = int(time.time())
        logger.info(f"Registering collector {self.collector_id}")
        
        # Add to active set
        self.redis.sadd('dvmdash:collectors:active', self.collector_id)
        
        # Store registration time in collectors hash
        self.redis.hset(f'collectors:{self.collector_id}', 'registered_at', current_time)
        
        # Start heartbeat
        await self._update_heartbeat()
        self._start_heartbeat()
        
        # Set a flag for the coordinator to distribute relays
        logger.info(f"Requesting relay distribution for new collector {self.collector_id}")
        self.redis.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
        self.redis.set('dvmdash:settings:last_change', current_time)
        
    def _start_heartbeat(self):
        """Start the heartbeat background task"""
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
    async def _heartbeat_loop(self):
        """Periodically update heartbeat timestamp"""
        while True:
            try:
                await self._update_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(5)  # Brief delay before retry
                
    async def _update_heartbeat(self):
        """Update collector heartbeat timestamp"""
        current_time = int(time.time())
        
        # Update heartbeat in Redis
        # Use a longer expiration time (120 seconds) to ensure heartbeats don't expire between health checks
        # This prevents false "no heartbeat" detections when the coordinator checks every 60 seconds
        self.redis.set(
            f'dvmdash:collector:{self.collector_id}:heartbeat',
            current_time,
            ex=120  # 2 minutes, longer than the health check interval (60 seconds)
        )
        
        # Also update in the collectors hash for the admin UI
        with self.redis.pipeline() as pipe:
            # Get current collector data
            collector_data = self.redis.hgetall(f'collectors:{self.collector_id}')
            if not collector_data:
                collector_data = {}
            
            # Update heartbeat
            collector_data['heartbeat'] = str(current_time)
            
            # Save back to Redis
            for key, value in collector_data.items():
                pipe.hset(f'collectors:{self.collector_id}', key, value)
            
            pipe.execute()
        
        logger.debug(f"Updated heartbeat for collector {self.collector_id} to {current_time}")
        
    async def shutdown(self):
        """Clean up collector registration on shutdown"""
        logger.info(f"Shutting down collector {self.collector_id}")
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self.redis.srem('dvmdash:collectors:active', self.collector_id)
        self.redis.delete(f'dvmdash:collector:{self.collector_id}:heartbeat')
        self.redis.delete(f'dvmdash:collector:{self.collector_id}:metrics')
        self.redis.delete(f'dvmdash:collector:{self.collector_id}:relays')

class RelayManager:
    """Manages relay assignments and metrics tracking"""
    
    def __init__(self, redis_client: Redis, collector_id: str):
        self.redis = redis_client
        self.collector_id = collector_id
        self.metrics_retention = 24 * 60 * 60  # 24 hours in seconds
        self._assigned_relays = {}  # Cache of assigned relays
        self._last_config_check = 0
        self.config_check_interval = 30  # seconds

    @staticmethod
    def get_all_relays(redis_client: Redis) -> Dict[str, Dict]:
        """Get all configured relays and their settings"""
        relays = redis_client.get('dvmdash:settings:relays')
        return json.loads(relays) if relays else {}

    @staticmethod
    def add_relay(redis_client: Redis, relay_url: str, activity: str = "normal") -> bool:
        """Add a new relay to the configuration"""
        try:
            with redis_client.pipeline() as pipe:
                # Add relay to settings
                current = pipe.get('dvmdash:settings:relays').execute()[0]
                relays = json.loads(current) if current else {}
                
                if relay_url in relays:
                    return False
                
                relays[relay_url] = {
                    "activity": activity,
                    "added_at": int(time.time()),
                    "added_by": "admin"
                }
                
                # Update settings and increment config version
                pipe.set('dvmdash:settings:relays', json.dumps(relays))
                pipe.incr('dvmdash:settings:config_version')
                pipe.set('dvmdash:settings:last_change', int(time.time()))
                pipe.execute()
                return True
        except Exception as e:
            logger.error(f"Error adding relay: {e}")
            return False

    @staticmethod
    def update_relay_activity(redis_client: Redis, relay_url: str, activity: str) -> bool:
        """Update a relay's activity level"""
        try:
            with redis_client.pipeline() as pipe:
                current = pipe.get('dvmdash:settings:relays').execute()[0]
                relays = json.loads(current) if current else {}
                
                if relay_url not in relays:
                    return False
                
                relays[relay_url]["activity"] = activity
                
                pipe.set('dvmdash:settings:relays', json.dumps(relays))
                pipe.incr('dvmdash:settings:config_version')
                pipe.set('dvmdash:settings:last_change', int(time.time()))
                pipe.execute()
                return True
        except Exception as e:
            logger.error(f"Error updating relay activity: {e}")
            return False

    @staticmethod
    def remove_relay(redis_client: Redis, relay_url: str) -> bool:
        """Remove a relay from the configuration"""
        try:
            with redis_client.pipeline() as pipe:
                current = pipe.get('dvmdash:settings:relays').execute()[0]
                relays = json.loads(current) if current else {}
                
                if relay_url not in relays:
                    return False
                
                del relays[relay_url]
                
                pipe.set('dvmdash:settings:relays', json.dumps(relays))
                pipe.incr('dvmdash:settings:config_version')
                pipe.set('dvmdash:settings:last_change', int(time.time()))
                pipe.execute()
                return True
        except Exception as e:
            logger.error(f"Error removing relay: {e}")
            return False

    @staticmethod
    def get_outdated_collectors(redis_client: Redis) -> List[str]:
        """Get list of collector IDs that need to be rebooted"""
        try:
            current_version = redis_client.get('dvmdash:settings:config_version')
            if not current_version:
                return []

            collectors = redis_client.smembers('dvmdash:collectors:active')
            outdated = []
            
            for collector_id in collectors:
                collector_version = redis_client.get(f'dvmdash:collector:{collector_id}:config_version')
                if not collector_version or int(collector_version) != int(current_version):
                    outdated.append(collector_id)
            
            return outdated
        except Exception as e:
            logger.error(f"Error checking outdated collectors: {e}")
            return []

    @staticmethod
    def distribute_relays(redis_client: Redis) -> bool:
        """
        Distribute relays across active collectors.
        Rules:
        1. Maximum 3 relays per collector
        2. Try to distribute high-activity relays evenly
        3. Distribute remaining relays evenly
        """
        try:
            logger.info("Starting relay distribution...")
            with redis_client.pipeline() as pipe:
                # Get current configuration
                relays_config = RelayManager.get_all_relays(redis_client)
                logger.info(f"Found {len(relays_config)} relays in configuration")
                
                # If no relays are configured, check if we need to initialize from config
                if not relays_config:
                    logger.warning("No relays found in Redis, checking if we need to initialize from config")
                    # Try to get relays from config:relays (without dvmdash: prefix)
                    config_relays = redis_client.get('config:relays')
                    if config_relays:
                        try:
                            relays_dict = json.loads(config_relays)
                            logger.info(f"Found {len(relays_dict)} relays in config:relays, copying to dvmdash:settings:relays")
                            # Copy to dvmdash:settings:relays
                            redis_client.set('dvmdash:settings:relays', config_relays)
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
                    redis_client.set('dvmdash:settings:relays', json.dumps(default_relays))
                    relays_config = default_relays
                    logger.info(f"Created default relay configuration with {len(default_relays)} relays")
                
                collectors = list(redis_client.smembers('dvmdash:collectors:active'))
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
                    
                    logger.info(f"Assigned {len(relays)} relays to collector {collector_id}")
                
                pipe.execute()
                logger.info("Relay distribution completed successfully")
                return True

        except Exception as e:
            logger.error(f"Error distributing relays: {e}")
            logger.error(traceback.format_exc())
            return False
        
    async def get_assigned_relays(self) -> List[str]:
        """Get list of relays assigned to this collector"""
        current_time = time.time()
        
        # Only check Redis if enough time has passed
        if current_time - self._last_config_check >= self.config_check_interval:
            # Try to get relays from dvmdash:collector:{id}:relays
            assigned = self.redis.get(f'dvmdash:collector:{self.collector_id}:relays')
            if assigned:
                try:
                    self._assigned_relays = json.loads(assigned)
                    logger.info(f"Found {len(self._assigned_relays)} relays assigned to collector {self.collector_id}")
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding relays JSON: {assigned}")
            
            # If no relays assigned, request relay distribution from coordinator
            if not self._assigned_relays:
                logger.warning(f"No relays assigned to collector {self.collector_id}, requesting relay distribution")
                
                # Request relay distribution from coordinator
                self.redis.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
                self.redis.set('dvmdash:settings:last_change', int(time.time()))
                
                # Wait a moment for distribution to take effect
                await asyncio.sleep(3)  # Wait a bit longer to give coordinator time to respond
                
                # Try again
                assigned = self.redis.get(f'dvmdash:collector:{self.collector_id}:relays')
                if assigned:
                    try:
                        self._assigned_relays = json.loads(assigned)
                        logger.info(f"Found {len(self._assigned_relays)} relays assigned to collector {self.collector_id} after distribution")
                    except json.JSONDecodeError as e:
                        logger.error(f"Error decoding relays JSON after distribution: {assigned}")
                
            self._last_config_check = current_time
            
        if not self._assigned_relays:
            # If we still don't have relays, raise exception
            logger.error(f"Empty relay assignment for collector {self.collector_id}")
            raise ValueError(f"Empty relay assignment for collector {self.collector_id}")
            
        return list(self._assigned_relays.keys())
    
    def update_relay_metrics(self, relay_url: str, event_id: str):
        """Update metrics for a relay after receiving an event"""
        current_time = int(time.time())
        
        # Update collector-specific metrics
        metrics_key = f'dvmdash:collector:{self.collector_id}:metrics:{relay_url}'
        pipe = self.redis.pipeline()
        
        # Update in dvmdash:collector:{id}:metrics:{relay_url}
        pipe.hset(metrics_key, 'last_event', current_time)
        pipe.hincrby(metrics_key, 'event_count', 1)
        pipe.expire(metrics_key, self.metrics_retention)
        
        # Also update in the collectors hash for the admin UI
        metrics_key_alt = f'collectors:{self.collector_id}:metrics:{relay_url}'
        pipe.hset(metrics_key_alt, 'last_event', str(current_time))
        pipe.hincrby(metrics_key_alt, 'event_count', 1)
        
        pipe.execute()
        
        logger.debug(f"Updated metrics for relay {relay_url} on collector {self.collector_id}")
        
    async def sync_config_version(self):
        """Update the collector's config version to match current settings and request relay distribution"""
        current_version = self.redis.get('dvmdash:settings:config_version')
        if current_version:
            # Update in dvmdash:collector:{id}:config_version
            self.redis.set(
                f'dvmdash:collector:{self.collector_id}:config_version',
                current_version
            )
            
            # Also update in the collectors hash for the admin UI
            self.redis.hset(
                f'collectors:{self.collector_id}',
                'config_version',
                current_version
            )
            
            logger.info(f"Updated config version for collector {self.collector_id} to {current_version}")
            
            # Request relay distribution from coordinator
            self.redis.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
            self.redis.set('dvmdash:settings:last_change', int(time.time()))
