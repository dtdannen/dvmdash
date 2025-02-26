import uuid
import time
import json
import asyncio
from typing import Dict, List, Optional
from redis import Redis
import logging

logger = logging.getLogger(__name__)

class CollectorManager:
    """Manages collector registration, heartbeat, and status in Redis"""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.collector_id = str(uuid.uuid4())
        self.heartbeat_interval = 60  # seconds
        self._heartbeat_task = None
        
    async def register(self):
        """Register this collector instance in Redis"""
        logger.info(f"Registering collector {self.collector_id}")
        self.redis.sadd('dvmdash:collectors:active', self.collector_id)
        await self._update_heartbeat()
        self._start_heartbeat()
        
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
        self.redis.set(
            f'dvmdash:collector:{self.collector_id}:heartbeat',
            int(time.time()),
            ex=self.heartbeat_interval * 2
        )
        
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
        1. Maximum 2 high-activity relays per collector
        2. Try to distribute high-activity relays evenly
        3. Distribute remaining relays evenly
        """
        try:
            with redis_client.pipeline() as pipe:
                # Get current configuration
                relays_config = RelayManager.get_all_relays(redis_client)
                collectors = list(redis_client.smembers('dvmdash:collectors:active'))
                
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

                # Calculate distribution
                assignments = {c: [] for c in collectors}
                
                # First distribute high-activity relays (max 2 per collector)
                collector_index = 0
                for relay in high_activity:
                    while len(assignments[collectors[collector_index]]) >= 2:
                        collector_index = (collector_index + 1) % len(collectors)
                    assignments[collectors[collector_index]].append(relay)
                    collector_index = (collector_index + 1) % len(collectors)

                # Then distribute normal relays
                collector_index = 0
                for relay in normal_activity:
                    assignments[collectors[collector_index]].append(relay)
                    collector_index = (collector_index + 1) % len(collectors)

                # Update Redis with new assignments
                for collector_id, relays in assignments.items():
                    pipe.set(
                        f'dvmdash:collector:{collector_id}:relays',
                        json.dumps({r: relays_config[r] for r in relays})
                    )
                
                pipe.execute()
                return True

        except Exception as e:
            logger.error(f"Error distributing relays: {e}")
            return False
        
    async def get_assigned_relays(self) -> List[str]:
        """Get list of relays assigned to this collector"""
        current_time = time.time()
        
        # Only check Redis if enough time has passed
        if current_time - self._last_config_check >= self.config_check_interval:
            assigned = self.redis.get(f'dvmdash:collector:{self.collector_id}:relays')
            if assigned:
                self._assigned_relays = json.loads(assigned)
            self._last_config_check = current_time
            
        return list(self._assigned_relays.keys())
    
    def update_relay_metrics(self, relay_url: str, event_id: str):
        """Update metrics for a relay after receiving an event"""
        current_time = int(time.time())
        
        # Update collector-specific metrics
        metrics_key = f'dvmdash:collector:{self.collector_id}:metrics:{relay_url}'
        pipe = self.redis.pipeline()
        pipe.hset(metrics_key, 'last_event', current_time)
        pipe.hincrby(metrics_key, 'event_count', 1)
        pipe.expire(metrics_key, self.metrics_retention)
        pipe.execute()
        
    async def sync_config_version(self):
        """Update the collector's config version to match current settings"""
        current_version = self.redis.get('dvmdash:settings:config_version')
        if current_version:
            self.redis.set(
                f'dvmdash:collector:{self.collector_id}:config_version',
                current_version
            )
