import redis
import uuid
from typing import Optional


class BatchProcessorRedisLock:
    def __init__(
        self,
        redis_client: redis.Redis,
        lock_name: str,
        expire_seconds: int = 10,
        owner_id: Optional[str] = None,
    ):
        self.redis = redis_client
        self.lock_name = lock_name
        self.expire_seconds = expire_seconds
        # Use provided owner_id or generate UUID
        self.lock_id = owner_id if owner_id else str(uuid.uuid4())

    def is_locked(self) -> bool:
        """Check if lock is currently held by anyone."""
        return bool(self.redis.exists(self.lock_name))

    def get_owner(self) -> Optional[str]:
        """Get the current owner of the lock."""
        return self.redis.get(self.lock_name)

    def attempt_acquire_once(self):
        success = self.redis.set(
            self.lock_name,
            self.lock_id,
            nx=True,  # Only set if key doesn't exist
            ex=self.expire_seconds,  # Set expiration
        )

        if success:
            return True

        return False

    def release(self) -> bool:
        """
        Release the lock if we own it.

        Returns:
            bool: True if lock was released, False if we didn't own it
        """
        # Lua script to atomically check and delete the lock
        # Only delete if the value matches our lock_id
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        result = self.redis.eval(script, 1, self.lock_name, self.lock_id)
        return bool(result)

    def __enter__(self):
        """Context manager support."""
        success = self.attempt_acquire_once()
        if not success:
            raise TimeoutError("Could not acquire lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.release()
