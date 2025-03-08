import json
import time
from typing import Dict, List
from redis import Redis
import logging

logger = logging.getLogger(__name__)

class RelayConfigManager:
    """Manages relay configuration in Redis for the admin API"""

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
                # Check if collector is outdated based on config version
                # Include all collectors, even if they haven't sent a heartbeat yet
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
            with redis_client.pipeline() as pipe:
                # Get current configuration
                relays_config = RelayConfigManager.get_all_relays(redis_client)
                all_collectors = list(redis_client.smembers('dvmdash:collectors:active'))
                
                # Include all collectors in the active set, even if they haven't sent a heartbeat yet
                # Only remove collectors with very old heartbeats (30+ minutes)
                current_time = int(time.time())
                active_threshold = current_time - (30 * 60)
                collectors = []
                
                for collector_id in all_collectors:
                    heartbeat = redis_client.get(f'dvmdash:collector:{collector_id}:heartbeat')
                    # Include collectors without heartbeats (they might be starting up)
                    # Only remove collectors with heartbeats older than 30 minutes
                    if not heartbeat or int(heartbeat) >= active_threshold:
                        collectors.append(collector_id)
                    else:
                        # Remove from active set if heartbeat is too old
                        redis_client.srem('dvmdash:collectors:active', collector_id)
                
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
                    pipe.set(
                        f'dvmdash:collector:{collector_id}:relays',
                        json.dumps({r: relays_config[r] for r in relays})
                    )
                
                pipe.execute()
                return True

        except Exception as e:
            logger.error(f"Error distributing relays: {e}")
            return False
