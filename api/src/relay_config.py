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
                
                # Try to find the relay URL in the relays dictionary
                # First try exact match
                if relay_url in relays:
                    matched_url = relay_url
                else:
                    # Try to normalize URLs for comparison
                    # This handles cases where the URL might be encoded differently
                    normalized_input = relay_url.lower().replace('%3A', ':')
                    matched_url = None
                    for url in relays.keys():
                        normalized_url = url.lower().replace('%3A', ':')
                        if normalized_url == normalized_input:
                            matched_url = url
                            break
                
                if not matched_url:
                    logger.error(f"Relay not found for activity update: {relay_url}")
                    return False
                
                logger.info(f"Updating relay activity: {matched_url} to {activity}")
                relays[matched_url]["activity"] = activity
                
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
                
                # Try to find the relay URL in the relays dictionary
                # First try exact match
                if relay_url in relays:
                    matched_url = relay_url
                else:
                    # Try to normalize URLs for comparison
                    # This handles cases where the URL might be encoded differently
                    normalized_input = relay_url.lower().replace('%3A', ':')
                    matched_url = None
                    for url in relays.keys():
                        normalized_url = url.lower().replace('%3A', ':')
                        if normalized_url == normalized_input:
                            matched_url = url
                            break
                
                if not matched_url:
                    logger.error(f"Relay not found: {relay_url}")
                    return False
                
                logger.info(f"Removing relay: {matched_url}")
                del relays[matched_url]
                
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
                # Ensure collector_id is a string for Redis key
                collector_id_str = collector_id.decode('utf-8') if isinstance(collector_id, bytes) else collector_id
                
                # Check if collector is outdated based on config version
                # Include all collectors, even if they haven't sent a heartbeat yet
                collector_version = redis_client.get(f'dvmdash:collector:{collector_id_str}:config_version')
                if not collector_version or int(collector_version) != int(current_version):
                    outdated.append(collector_id)
            
            return outdated
        except Exception as e:
            logger.error(f"Error checking outdated collectors: {e}")
            return []

    @staticmethod
    def request_relay_distribution(redis_client: Redis) -> bool:
        """
        Set a flag in Redis to request relay distribution from the coordinator.
        This is more robust than directly triggering distribution from the API.
        """
        try:
            # Set the last_change timestamp to trigger redistribution
            redis_client.set('dvmdash:settings:last_change', int(time.time()))
            # Set a specific flag to request distribution
            redis_client.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
            return True
        except Exception as e:
            logger.error(f"Error requesting relay distribution: {e}")
            return False
