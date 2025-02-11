# tests/test_batch_processor.py
import pytest
from batch_processor.src.main import BatchProcessor, MetricsDiff
import json
import os


def load_sample_events():
    with open("tests/test_data/sample_events.json") as f:
        return json.load(f)


class TestBatchProcessor:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.events = load_sample_events()
        self.processor = BatchProcessor(
            pg_pool=None,  # Mock these for unit tests
            mongo_client=None,
            redis_url=f"redis://{os.getenv('REDIS_HOST', 'redis')}:6379/0",
        )

    def test_metrics_diff_computation(self):
        diff = self.processor.compute_batch_diff(self.events)
        assert diff.job_requests == 1
        assert diff.job_results == 1
        assert len(diff.new_user_ids) == 1
        assert len(diff.new_dvm_ids) == 1
        assert diff.sats_earned == 100

    def test_empty_batch(self):
        diff = self.processor.compute_batch_diff([])
        assert diff.job_requests == 0
        assert diff.job_results == 0
        assert len(diff.new_user_ids) == 0
        assert len(diff.new_dvm_ids) == 0
        assert diff.sats_earned == 0

    def test_invalid_event_handling(self):
        invalid_events = [
            {"id": "bad1"},  # Missing kind
            {"id": "bad2", "kind": 5100},  # Missing pubkey
        ]
        diff = self.processor.compute_batch_diff(invalid_events)
        assert diff.job_requests == 0
        assert diff.job_results == 0
