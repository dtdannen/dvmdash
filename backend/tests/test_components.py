# tests/integration/test_components.py

import pytest
import asyncio
import redis
import motor.motor_asyncio
import asyncpg
from datetime import datetime
import json
from typing import Dict, List

# Import your components (adjust paths as needed)
from batch_processor.src.main import BatchProcessor, MetricsDiff
from shared.models.dvm_event import EventKind  # Assuming you have this


# Fixtures for test data
@pytest.fixture
def sample_events() -> List[Dict]:
    """Sample events representing different DVM scenarios."""
    return [
        {
            "id": "event1",
            "kind": 5100,  # Job request
            "pubkey": "user1",
            "created_at": 1677483647,
            "tags": [],
        },
        {
            "id": "event2",
            "kind": 6100,  # Job result
            "pubkey": "dvm1",
            "created_at": 1677483648,
            "tags": [["amount", "100"]],  # 100 sats earned
        },
        {
            "id": "event3",
            "kind": 5100,  # Another job request
            "pubkey": "user2",
            "created_at": 1677483649,
            "tags": [],
        },
    ]


# Redis Deduplication Tests
class TestRedisDeduplication:
    @pytest.fixture(autouse=True)
    async def setup(self):
        """Setup test Redis connection and cleanup after."""
        self.redis = redis.Redis(
            host="localhost", port=6379, db=15  # Use separate DB for testing
        )
        yield
        self.redis.flushdb()  # Clean up after tests

    async def test_duplicate_detection(self):
        """Test that Redis correctly handles duplicate events."""
        dedup_set = "test_processed_events"

        # First event should be accepted
        event_id = "test_event_1"
        is_new = self.redis.sadd(dedup_set, event_id)
        assert is_new == 1

        # Same event should be rejected
        is_new = self.redis.sadd(dedup_set, event_id)
        assert is_new == 0

    async def test_bounded_set_cleanup(self):
        """Test that old events get cleaned up when limit reached."""
        dedup_set = "test_processed_events"
        zset_key = "test_event_timestamps"
        max_events = 5

        # Add more than max_events
        for i in range(7):
            event_id = f"event_{i}"
            self.redis.sadd(dedup_set, event_id)
            self.redis.zadd(zset_key, {event_id: datetime.now().timestamp() + i})

        # Verify only max_events remain and oldest were removed
        assert self.redis.scard(dedup_set) == max_events
        assert not self.redis.sismember(dedup_set, "event_0")
        assert not self.redis.sismember(dedup_set, "event_1")


# Batch Processor Tests
class TestBatchProcessor:
    @pytest.fixture(autouse=True)
    async def setup(self):
        """Setup test database connections."""
        self.pg_pool = await asyncpg.create_pool(
            user="postgres",
            password="postgres",
            database="test_dvmdash",
            host="localhost",
        )
        self.mongo = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
        self.mongo.get_database("test_dvmdash")

        # Clean up test databases
        async with self.pg_pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE global_stats, users, dvms")
        await self.mongo.test_dvmdash.events.delete_many({})

        yield

        # Cleanup after tests
        await self.pg_pool.close()
        self.mongo.close()

    async def test_metrics_diff_computation(self, sample_events):
        """Test that MetricsDiff correctly computes changes."""
        processor = BatchProcessor(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo,
            redis_url="redis://localhost:6379/15",
        )

        diff = processor.compute_batch_diff(sample_events)

        # Verify diff calculations
        assert diff.job_requests == 2  # Two 51xx events
        assert diff.job_results == 1  # One 61xx event
        assert len(diff.new_user_ids) == 2  # Two unique users
        assert len(diff.new_dvm_ids) == 1  # One DVM
        assert diff.sats_earned == 100  # From the job result event

    async def test_postgres_updates(self, sample_events):
        """Test that PostgreSQL updates work correctly."""
        processor = BatchProcessor(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo,
            redis_url="redis://localhost:6379/15",
        )

        # Process batch and verify results
        success = await processor.process_batch(sample_events)
        assert success

        # Verify PostgreSQL updates
        async with self.pg_pool.acquire() as conn:
            stats = await conn.fetchrow(
                "SELECT * FROM global_stats ORDER BY timestamp DESC LIMIT 1"
            )
            assert stats["job_requests"] == 2
            assert stats["job_results"] == 1
            assert stats["total_sats_earned"] == 100

            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            assert user_count == 2

            dvm_count = await conn.fetchval("SELECT COUNT(*) FROM dvms")
            assert dvm_count == 1

    async def test_mongo_event_storage(self, sample_events):
        """Test that events are properly stored in MongoDB."""
        processor = BatchProcessor(
            pg_pool=self.pg_pool,
            mongo_client=self.mongo,
            redis_url="redis://localhost:6379/15",
        )

        # Process batch
        success = await processor.process_batch(sample_events)
        assert success

        # Verify MongoDB storage
        stored_count = await self.mongo.test_dvmdash.events.count_documents({})
        assert stored_count == len(sample_events)

        # Verify specific event details
        event = await self.mongo.test_dvmdash.events.find_one({"id": "event1"})
        assert event is not None
        assert event["kind"] == 5100


# Run tests with:
# pytest tests/integration/test_components.py -v --asyncio-mode=auto
