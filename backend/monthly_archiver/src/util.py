import redis
import uuid
import time
from typing import Optional


class RedisLock:
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
        # Use provided owner_id or generate UUID
        self.lock_id = owner_id if owner_id else str(uuid.uuid4())

    async def is_locked(self) -> bool:
        """Check if lock is currently held by anyone."""
        return bool(await self.redis.exists(self.lock_name))

    async def get_owner(self) -> Optional[str]:
        """Get the current owner of the lock."""
        return await self.redis.get(self.lock_name)

    async def attempt_acquire_once(self):
        success = await self.redis.set(
            self.lock_name,
            self.lock_id,
            nx=True,  # Only set if key doesn't exist
            ex=self.expire_seconds,  # Set expiration
        )

        if success:
            return True

        return False

    def acquire(self) -> bool:
        """
        Attempt to acquire the lock.

        Returns:
            bool: True if lock was acquired, False otherwise
        """
        for attempt in range(self.retry_times):
            # Try to set the lock with our unique ID
            success = self.redis.set(
                self.lock_name,
                self.lock_id,
                nx=True,  # Only set if key doesn't exist
                ex=self.expire_seconds,  # Set expiration
            )

            if success:
                return True

            if attempt < self.retry_times - 1:
                time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff

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


# Usage example:
def example_usage():
    # Initialize Redis client
    redis_client = redis.Redis(host="localhost", port=6379, db=0)

    # Create a lock instance
    lock = RedisLock(redis_client, "my_lock", expire_seconds=10)

    # Method 1: Manual acquire/release
    if lock.acquire():
        try:
            print("Lock acquired, doing work...")
            # Your critical section code here
            time.sleep(2)
        finally:
            lock.release()
    else:
        print("Could not acquire lock")

    # Method 2: Using context manager (recommended)
    try:
        with RedisLock(redis_client, "my_lock", expire_seconds=10) as lock:
            print("Lock acquired, doing work...")
            # Your critical section code here
            time.sleep(2)
    except TimeoutError:
        print("Could not acquire lock")
