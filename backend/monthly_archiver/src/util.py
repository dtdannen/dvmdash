import redis
import uuid
import time
from typing import Optional


class ArchiverRedisLock:
    def __init__(
        self,
        redis_client: redis.Redis,
        lock_name: str,
        expire_seconds: int = 10,
        retry_times: int = 3,
        retry_delay: float = 0.2,
        owner_id: Optional[str] = None,
    ):
        self.redis = redis_client
        self.lock_name = lock_name
        self.expire_seconds = expire_seconds
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.lock_id = owner_id if owner_id else str(uuid.uuid4())

    def is_locked(self) -> bool:
        """Check if lock is currently held by anyone."""
        return bool(self.redis.exists(self.lock_name))

    def get_owner(self) -> Optional[str]:
        """Get the current owner of the lock."""
        return self.redis.get(self.lock_name)

    def acquire_with_retry(self) -> bool:
        """Attempt to acquire the lock with retries and backoff."""
        for attempt in range(self.retry_times):
            success = self.redis.set(
                self.lock_name,
                self.lock_id,
                nx=True,
                ex=self.expire_seconds,
            )

            if success:
                return True

            if attempt < self.retry_times - 1:
                time.sleep(self.retry_delay * (attempt + 1))

        return False

    def release(self) -> bool:
        """Release the lock if we own it."""
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
        """Async context manager for retry-based acquisition."""
        success = self.acquire_with_retry()
        if not success:
            raise TimeoutError("Could not acquire lock after retries")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Async context manager cleanup."""
        self.release()
