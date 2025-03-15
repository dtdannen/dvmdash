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
        logger.info(f"[REDIS_DEBUG] Starting registration for collector {self.collector_id}")
        
        try:
            # Add to active set
            result = self.redis.sadd('dvmdash:collectors:active', self.collector_id)
            logger.info(f"[REDIS_DEBUG] Added to active set: {result}")
            
            # Store registration time in collector hash
            result = self.redis.hset(f'dvmdash:collector:{self.collector_id}', 'registered_at', current_time)
            logger.info(f"[REDIS_DEBUG] Stored registration time: {result}")
            
            # Start heartbeat
            logger.info(f"[REDIS_DEBUG] Starting heartbeat for {self.collector_id}")
            await self._update_heartbeat()
            self._start_heartbeat()
            
            # Set a flag for the coordinator to distribute relays
            logger.info(f"[REDIS_DEBUG] Requesting relay distribution for new collector {self.collector_id}")
            result1 = self.redis.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
            result2 = self.redis.set('dvmdash:settings:last_change', current_time)
            logger.info(f"[REDIS_DEBUG] Distribution request set: {result1}, last_change set: {result2}")
            
            # Verify registration
            is_active = self.redis.sismember('dvmdash:collectors:active', self.collector_id)
            logger.info(f"[REDIS_DEBUG] Verification - collector in active set: {is_active}")
            
            # Wait for nsec key assignment
            await self._wait_for_nsec_key()
        except Exception as e:
            logger.error(f"[REDIS_DEBUG] Error during collector registration: {e}")
            logger.error(traceback.format_exc())
            raise
        
    async def _wait_for_nsec_key(self):
        """Wait for nsec key assignment from coordinator"""
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            nsec_key = self.redis.get(f"dvmdash:collector:{self.collector_id}:nsec_key")
            if nsec_key:
                logger.info(f"[REDIS_DEBUG] Received nsec key assignment from coordinator")
                return
                
            logger.info(f"[REDIS_DEBUG] Waiting for nsec key assignment (attempt {attempt+1}/{max_retries})")
            await asyncio.sleep(retry_delay)
            retry_delay = min(10, retry_delay * 2)  # Exponential backoff, max 10 seconds
        
        logger.warning("[REDIS_DEBUG] Did not receive nsec key assignment after maximum retries")
    
    def _start_heartbeat(self):
        """Start the heartbeat background task"""
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
    async def _heartbeat_loop(self):
        """Periodically update heartbeat timestamp"""
        last_success = time.time()
        while True:
            try:
                current_time = time.time()
                time_since_last = current_time - last_success
                
                # Log if it's been a while since the last successful heartbeat
                if time_since_last > 30:  # Log if more than 30 seconds have passed
                    logger.warning(f"[HEARTBEAT] Long delay since last successful heartbeat: {time_since_last:.1f} seconds")
                
                await self._update_heartbeat()
                last_success = time.time()
                
                # Log successful heartbeat periodically (every 10 heartbeats)
                if int(last_success) % (self.heartbeat_interval * 10) < self.heartbeat_interval:
                    logger.info(f"[HEARTBEAT] Successfully updated heartbeat at {time.strftime('%H:%M:%S', time.localtime(last_success))}")
                
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error in heartbeat loop: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)  # Brief delay before retry
                
    async def _update_heartbeat(self):
        """Update collector heartbeat timestamp"""
        current_time = int(time.time())
        start_time = time.time()
        
        try:
            # Update heartbeat in Redis - single location in the hash
            result = self.redis.hset(
                f'dvmdash:collector:{self.collector_id}',
                'heartbeat', current_time
            )
            
            # Set TTL on the hash
            self.redis.expire(
                f'dvmdash:collector:{self.collector_id}',
                120  # 2 minutes, longer than the health check interval (60 seconds)
            )
            
            logger.debug(f"[HEARTBEAT] Updated heartbeat key: {result}")
            
            # Verify heartbeat was set
            stored_heartbeat = self.redis.hget(f'dvmdash:collector:{self.collector_id}', 'heartbeat')
            logger.debug(f"[HEARTBEAT] Verification - stored heartbeat: {stored_heartbeat}")
            
            # Log if the heartbeat update took a long time
            elapsed = time.time() - start_time
            if elapsed > 1.0:  # Log if it took more than 1 second
                logger.warning(f"[HEARTBEAT] Heartbeat update took {elapsed:.2f} seconds")
            
        except Exception as e:
            logger.error(f"[HEARTBEAT] Error updating heartbeat: {e}")
            logger.error(traceback.format_exc())
        
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
        self.redis.delete(f'dvmdash:collector:{self.collector_id}')
        self.redis.delete(f'dvmdash:collector:{self.collector_id}:relays')
        
        # Clean up metrics keys
        metrics_keys = self.redis.keys(f'dvmdash:collector:{self.collector_id}:metrics:*')
        if metrics_keys:
            self.redis.delete(*metrics_keys)

class RelayManager:
    """Manages relay assignments and metrics tracking"""
    
    def __init__(self, redis_client: Redis, collector_id: str):
        self.redis = redis_client
        self.collector_id = collector_id
        self.metrics_retention = 24 * 60 * 60  # 24 hours in seconds
        self._assigned_relays = {}  # Cache of assigned relays
        self._last_config_check = 0
        self.config_check_interval = 30  # seconds
        self._last_metrics_cleanup = 0
        self.metrics_cleanup_interval = 3600  # Clean up metrics keys once per hour

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
        
        logger.info(f"[REDIS_DEBUG] Getting assigned relays for collector {self.collector_id}")
        
        try:
            # Only check Redis if enough time has passed
            if current_time - self._last_config_check >= self.config_check_interval:
                # Try to get relays from dvmdash:collector:{id}:relays
                relay_key = f'dvmdash:collector:{self.collector_id}:relays'
                logger.info(f"[REDIS_DEBUG] Checking Redis key: {relay_key}")
                assigned = self.redis.get(relay_key)
                
                if assigned:
                    logger.info(f"[REDIS_DEBUG] Found relay assignment data: {assigned[:100]}...")
                    try:
                        self._assigned_relays = json.loads(assigned)
                        logger.info(f"[REDIS_DEBUG] Successfully parsed {len(self._assigned_relays)} relays assigned to collector {self.collector_id}")
                    except json.JSONDecodeError as e:
                        logger.error(f"[REDIS_DEBUG] Error decoding relays JSON: {e}")
                        logger.error(f"[REDIS_DEBUG] Raw relay data: {assigned}")
                else:
                    logger.info(f"[REDIS_DEBUG] No relay assignment found in Redis for key: {relay_key}")
                
                # If no relays assigned, request relay distribution from coordinator
                if not self._assigned_relays:
                    logger.warning(f"[REDIS_DEBUG] No relays assigned to collector {self.collector_id}, requesting relay distribution")
                    
                    # Request relay distribution from coordinator
                    result1 = self.redis.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
                    result2 = self.redis.set('dvmdash:settings:last_change', int(time.time()))
                    logger.info(f"[REDIS_DEBUG] Distribution request results: {result1}, {result2}")
                    
                    # Wait a moment for distribution to take effect
                    logger.info(f"[REDIS_DEBUG] Waiting for distribution to take effect...")
                    await asyncio.sleep(3)  # Wait a bit longer to give coordinator time to respond
                    
                    # Try again
                    logger.info(f"[REDIS_DEBUG] Checking for relay assignment after distribution request")
                    assigned = self.redis.get(f'dvmdash:collector:{self.collector_id}:relays')
                    if assigned:
                        logger.info(f"[REDIS_DEBUG] Found relay assignment after distribution: {assigned[:100]}...")
                        try:
                            self._assigned_relays = json.loads(assigned)
                            logger.info(f"[REDIS_DEBUG] Successfully parsed {len(self._assigned_relays)} relays after distribution")
                        except json.JSONDecodeError as e:
                            logger.error(f"[REDIS_DEBUG] Error decoding relays JSON after distribution: {e}")
                            logger.error(f"[REDIS_DEBUG] Raw relay data after distribution: {assigned}")
                    else:
                        logger.error(f"[REDIS_DEBUG] Still no relay assignment after distribution request")
                    
                self._last_config_check = current_time
                
            # Check if we have relays now
            if self._assigned_relays:
                logger.info(f"[REDIS_DEBUG] Returning {len(self._assigned_relays)} assigned relays: {list(self._assigned_relays.keys())}")
            else:
                # Check if coordinator is running
                coordinator_heartbeat = self.redis.get('dvmdash:coordinator:heartbeat')
                logger.error(f"[REDIS_DEBUG] Coordinator heartbeat: {coordinator_heartbeat}")
                
                # Check active collectors
                active_collectors = self.redis.smembers('dvmdash:collectors:active')
                logger.error(f"[REDIS_DEBUG] Active collectors: {active_collectors}")
                
                # If we still don't have relays, raise exception
                logger.error(f"[REDIS_DEBUG] Empty relay assignment for collector {self.collector_id}")
                raise ValueError(f"Empty relay assignment for collector {self.collector_id}")
                
            return list(self._assigned_relays.keys())
            
        except Exception as e:
            if isinstance(e, ValueError) and "Empty relay assignment" in str(e):
                # Re-raise the expected ValueError
                raise
            
            # Log other unexpected errors
            logger.error(f"[REDIS_DEBUG] Unexpected error getting assigned relays: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def update_relay_metrics(self, relay_url: str, event_id: str):
        """Update metrics for a relay after receiving an event"""
        current_time = int(time.time())
        
        # Normalize relay URL to ensure it has a trailing slash
        normalized_url = relay_url if relay_url.endswith('/') else f"{relay_url}/"
        
        # Update metrics in a single location
        metrics_key = f'dvmdash:collector:{self.collector_id}:metrics:{normalized_url}'
        pipe = self.redis.pipeline()
        
        # Update in metrics hash
        pipe.hset(metrics_key, 'last_event', current_time)
        pipe.hincrby(metrics_key, 'event_count', 1)
        pipe.expire(metrics_key, self.metrics_retention)  # Set TTL for automatic expiration
        
        pipe.execute()
        
        logger.debug(f"Updated metrics for relay {normalized_url} on collector {self.collector_id}")
        
        # Periodically clean up old metrics keys
        self._maybe_cleanup_metrics(current_time)
        
    def _maybe_cleanup_metrics(self, current_time):
        """Periodically clean up old metrics keys"""
        if current_time - self._last_metrics_cleanup < self.metrics_cleanup_interval:
            return
            
        try:
            # Set the last cleanup time first to avoid repeated cleanup attempts if it fails
            self._last_metrics_cleanup = current_time
            
            # Get all metrics keys for this collector
            metrics_pattern = f'dvmdash:collector:{self.collector_id}:metrics:*'
            metrics_keys = self.redis.keys(metrics_pattern)
            
            if not metrics_keys:
                return
                
            logger.info(f"[METRICS] Found {len(metrics_keys)} metrics keys for cleanup check")
            
            # Get current relay assignments
            relays_json = self.redis.get(f'dvmdash:collector:{self.collector_id}:relays')
            current_relays = []
            if relays_json:
                try:
                    relays_dict = json.loads(relays_json)
                    current_relays = list(relays_dict.keys())
                except json.JSONDecodeError:
                    logger.error(f"[METRICS] Error decoding relays JSON: {relays_json}")
            
            # Find metrics keys for relays that are no longer assigned
            keys_to_delete = []
            for key in metrics_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                # Extract relay URL from key
                relay_url = key_str.replace(f'dvmdash:collector:{self.collector_id}:metrics:', '')
                
                # Check if the relay URL (with or without trailing slash) is in current_relays
                relay_url_no_slash = relay_url.rstrip('/')
                relay_matches = False
                
                for current_relay in current_relays:
                    current_relay_no_slash = current_relay.rstrip('/')
                    if relay_url_no_slash == current_relay_no_slash:
                        relay_matches = True
                        break
                
                if not relay_matches:
                    keys_to_delete.append(key)
            
            # Delete orphaned metrics keys
            if keys_to_delete:
                logger.info(f"[METRICS] Cleaning up {len(keys_to_delete)} orphaned metrics keys")
                self.redis.delete(*keys_to_delete)
        
        except Exception as e:
            logger.error(f"[METRICS] Error cleaning up metrics keys: {e}")
            logger.error(traceback.format_exc())

    async def sync_config_version(self):
        """Update the collector's config version to match current settings and request relay distribution"""
        current_version = self.redis.get('dvmdash:settings:config_version')
        if current_version:
            # Update in collector hash
            self.redis.hset(
                f'dvmdash:collector:{self.collector_id}',
                'config_version',
                current_version
            )
            
            logger.info(f"Updated config version for collector {self.collector_id} to {current_version}")
            
            # Request relay distribution from coordinator
            self.redis.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
            self.redis.set('dvmdash:settings:last_change', int(time.time()))
