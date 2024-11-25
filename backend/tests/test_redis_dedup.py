# tests/test_redis_dedup.py
import pytest
import redis
import json
import os


class TestRedisDedup:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.redis = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)
        self.dedup_set = "dvmdash_processed_events"
        yield
        self.redis.delete(self.dedup_set)

    def test_new_event_accepted(self):
        event_id = "test_event_1"
        is_new = self.redis.sadd(self.dedup_set, event_id)
        assert is_new == 1
        assert self.redis.sismember(self.dedup_set, event_id)

    def test_duplicate_rejected(self):
        event_id = "test_event_2"
        first_add = self.redis.sadd(self.dedup_set, event_id)
        second_add = self.redis.sadd(self.dedup_set, event_id)
        assert first_add == 1
        assert second_add == 0

    def test_multiple_events(self):
        event_ids = ["event1", "event2", "event3"]
        for event_id in event_ids:
            self.redis.sadd(self.dedup_set, event_id)
        assert self.redis.scard(self.dedup_set) == 3
