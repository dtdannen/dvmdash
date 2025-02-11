# backend/celery_worker/src/deduplicator.py
from datetime import datetime
import redis
import logging
from typing import Optional, Tuple
import time

logger = logging.getLogger(__name__)


class BoundedEventDeduplicator:
    def __init__(
        self,
        redis_url: str,
        sentinel_kwargs: Optional[dict] = None,
        max_events: int = 1_000_000,
    ):
        self.redis = redis.from_url(redis_url)
        self.set_key = "dvmdash_processed_events"
        self.zset_key = "dvmdash_event_timestamps"
        self.max_events = max_events
        self.cleanup_threshold = 0.98
        self.cleanup_batch = 10_000

        if sentinel_kwargs:
            from redis.sentinel import Sentinel

            sentinel = Sentinel(
                sentinel_kwargs["sentinel_hosts"],
                socket_timeout=sentinel_kwargs.get("socket_timeout", 0.1),
            )
            self.redis = sentinel.master_for(
                sentinel_kwargs["service_name"],
                socket_timeout=sentinel_kwargs.get("socket_timeout", 0.1),
            )
        else:
            self.redis = redis.from_url(redis_url)

    def _get_current_size(self) -> int:
        """Get current number of events in the set."""
        return self.redis.scard(self.set_key)

    def _needs_cleanup(self) -> bool:
        """Check if we need to remove old events."""
        current_size = self._get_current_size()
        return current_size >= (self.max_events * self.cleanup_threshold)

    def _cleanup_oldest_events(self) -> Tuple[int, int]:
        """
        Remove oldest events when approaching capacity.
        Returns (number_removed, new_size)
        """
        try:
            # Get timestamp for oldest events to remove
            current_size = self._get_current_size()
            if current_size <= self.max_events:
                return 0, current_size

            # Calculate how many events to remove
            # Remove enough to get below threshold
            target_size = int(self.max_events * 0.95)  # Aim for 95% capacity
            to_remove = current_size - target_size

            # Get the oldest events from the sorted set
            oldest_events = self.redis.zrange(
                self.zset_key,
                0,
                to_remove - 1,  # -1 because zrange end is inclusive
                withscores=True,
            )

            if not oldest_events:
                return 0, current_size

            # Remove from both set and sorted set in a pipeline
            with self.redis.pipeline() as pipe:
                # Remove from main set
                pipe.srem(self.set_key, *[event[0] for event in oldest_events])
                # Remove from timestamp sorted set
                pipe.zremrangebyrank(self.zset_key, 0, to_remove - 1)
                pipe.execute()

            new_size = self._get_current_size()
            logger.info(
                f"Cleaned up {len(oldest_events)} events. " f"New size: {new_size:,}"
            )
            return len(oldest_events), new_size

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0, self._get_current_size()

    def check_duplicate(self, event_id: str, timestamp: Optional[float] = None) -> bool:
        try:
            if timestamp is None:
                timestamp = time.time()

            with self.redis.pipeline() as pipe:
                # Execute both operations atomically
                pipe.sadd(self.set_key, event_id)
                pipe.zadd(self.zset_key, {event_id: timestamp})
                results = pipe.execute()

                is_new = results[0]  # Result of sadd
                if is_new and self._needs_cleanup():
                    removed, new_size = self._cleanup_oldest_events()
                    if removed > 0:
                        logger.info(
                            f"Cleanup triggered. Removed {removed:,} events. "
                            f"New size: {new_size:,}"
                        )

                return not is_new  # Return True if duplicate

        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False  # On error, treat as new event

    def get_stats(self) -> dict:
        """Get current statistics about the deduplication sets."""
        try:
            current_size = self._get_current_size()
            capacity_used = (current_size / self.max_events) * 100

            # Get timestamp range if events exist
            oldest_timestamp = newest_timestamp = None
            if current_size > 0:
                oldest = self.redis.zrange(self.zset_key, 0, 0, withscores=True)
                newest = self.redis.zrange(self.zset_key, -1, -1, withscores=True)

                if oldest and newest:
                    oldest_timestamp = oldest[0][1]
                    newest_timestamp = newest[0][1]

            memory_usage = self.redis.memory_usage(self.set_key)
            memory_usage_mb = memory_usage / (1024 * 1024) if memory_usage else 0

            return {
                "current_size": current_size,
                "max_size": self.max_events,
                "capacity_used_percent": round(capacity_used, 2),
                "memory_usage_mb": round(memory_usage_mb, 2),
                "oldest_event_time": datetime.fromtimestamp(
                    oldest_timestamp
                ).isoformat()
                if oldest_timestamp
                else None,
                "newest_event_time": datetime.fromtimestamp(
                    newest_timestamp
                ).isoformat()
                if newest_timestamp
                else None,
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}

    def health_check(self) -> Tuple[bool, str]:
        """
        Check if the deduplication system is healthy.
        Returns (is_healthy, message)
        """
        try:
            # Test basic Redis operations
            self.redis.ping()

            # Check if we're approaching capacity
            stats = self.get_stats()
            capacity_used = stats.get("capacity_used_percent", 0)

            if capacity_used >= 95:
                return False, f"System at {capacity_used}% capacity"

            # Check if cleanup is working
            if capacity_used >= self.cleanup_threshold * 100:
                removed, _ = self._cleanup_oldest_events()
                if removed == 0:
                    return False, "Cleanup failed to remove events"

            return True, "Deduplication system healthy"

        except redis.RedisError as e:
            return False, f"Redis connection error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"

    def increment_metrics(self, event_id: str, is_duplicate: bool) -> None:
        """Track metrics about deduplication"""
        timestamp = int(time.time())
        hour_key = f"dvmdash_dedup_metrics:{timestamp - (timestamp % 3600)}"

        with self.redis.pipeline() as pipe:
            # Increment total events and duplicates
            pipe.hincrby(hour_key, "total_events", 1)
            if is_duplicate:
                pipe.hincrby(hour_key, "duplicate_events", 1)

            # Set expiry for metrics (keep for 24 hours)
            pipe.expire(hour_key, 86400)
            pipe.execute()
