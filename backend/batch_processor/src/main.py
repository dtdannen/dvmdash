import os
import sys
import time
import asyncio
from datetime import datetime
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from collections import defaultdict
import asyncpg
import motor.motor_asyncio
import redis
import json
import base64
import traceback
from loguru import logger

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)


@dataclass
class MetricsDiff:
    """Represents the changes to be applied to global metrics"""

    job_requests: int = 0
    job_results: int = 0
    new_user_ids: Set[str] = None  # These are sets of new IDs to add
    new_dvm_ids: Set[str] = None  # We'll union these with existing sets
    new_kind_ids: Set[int] = None
    sats_earned: int = 0

    # Track for popularity metrics
    kind_request_counts: Dict[int, int] = None  # {kind_id: count}
    dvm_earnings: Dict[str, int] = None  # {dvm_id: sats}

    def __post_init__(self):
        # Initialize sets and dicts if None
        if self.new_user_ids is None:
            self.new_user_ids = set()
        if self.new_dvm_ids is None:
            self.new_dvm_ids = set()
        if self.new_kind_ids is None:
            self.new_kind_ids = set()
        if self.kind_request_counts is None:
            self.kind_request_counts = defaultdict(int)
        if self.dvm_earnings is None:
            self.dvm_earnings = defaultdict(int)


class BatchProcessor:
    def __init__(
        self,
        redis_url: str,
        pg_pool: asyncpg.Pool,
        mongo_client: motor.motor_asyncio.AsyncIOMotorClient,
        queue_name: str = "dvmdash",
        batch_size: int = 100,
        max_wait_seconds: int = 5,
    ):
        self.redis = redis.from_url(redis_url)
        self.pg_pool = pg_pool
        self.mongo = mongo_client
        self.queue_name = queue_name
        self.batch_size = batch_size
        self.max_wait_seconds = max_wait_seconds
        self.event_count = 0
        self.error_count = 0

    def extract_nostr_event(self, message: bytes) -> Dict:
        """Extract the Nostr event from a Celery task message in Redis."""
        try:
            # Parse the outer message
            message_data = json.loads(message)

            # Get the base64 encoded body
            if isinstance(message_data, str):
                message_data = json.loads(message_data)

            body = message_data.get("body")
            if not body:
                raise ValueError("No body found in message")

            # Decode the base64 body
            decoded_body = base64.b64decode(body).decode("utf-8")

            # The body contains a list with the task args and kwargs
            body_data = json.loads(decoded_body)

            # The event data should be the first argument
            if not isinstance(body_data, list) or len(body_data) < 1:
                raise ValueError("Invalid message structure")

            event_data = body_data[0][0]  # First item of first argument array
            if not isinstance(event_data, dict):
                raise ValueError("Event data is not a dictionary")

            return event_data

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse message: {str(e)}")
            logger.debug(f"Raw message: {message[:200]}...")  # First 200 chars
            raise

    async def get_batch_of_events(self) -> List[Dict]:
        """
        Get a batch of events from Redis queue.
        Uses BRPOP with timeout for the first event, then gets more if available.
        """
        events = []
        start_time = time.time()

        try:
            # Wait for first event with timeout
            result = self.redis.brpop(self.queue_name, timeout=self.max_wait_seconds)

            if result:
                _, message = result
                event = self.extract_nostr_event(message)
                if event:
                    events.append(event)

                # Quick grab any additional events up to batch_size
                while len(events) < self.batch_size:
                    if time.time() - start_time >= self.max_wait_seconds:
                        break

                    result = self.redis.lpop(self.queue_name)
                    if not result:
                        break

                    event = self.extract_nostr_event(result)
                    if event:
                        events.append(event)

        except Exception as e:
            logger.error(f"Error getting batch of events: {e}")
            logger.error(traceback.format_exc())

        return events

    def compute_batch_diff(self, events: List[Dict]) -> MetricsDiff:
        """Compute metric differences from a batch of events."""
        diff = MetricsDiff()

        for event in events:
            kind = event.get("kind")
            pubkey = event.get("pubkey")
            event_id = event.get("id", "NO_ID")

            if not kind or not pubkey:
                logger.warning(f"Event missing kind or pubkey: {event_id}")
                continue

            if 5000 <= kind < 6000:  # Job requests
                diff.job_requests += 1
                diff.new_user_ids.add(pubkey)
                diff.new_kind_ids.add(kind)
                diff.kind_request_counts[kind] += 1

            elif 6000 <= kind < 7000:  # Job results
                diff.job_results += 1
                diff.new_dvm_ids.add(pubkey)

                # Extract sats from tags if present
                for tag in event.get("tags", []):
                    if len(tag) >= 2 and tag[0] == "amount":
                        try:
                            sats = int(tag[1])
                            diff.sats_earned += sats
                            diff.dvm_earnings[pubkey] += sats
                        except (IndexError, ValueError):
                            logger.warning(f"Invalid amount tag in event {event_id}")
                            continue

        return diff

    async def apply_diff_to_postgres(self, diff: MetricsDiff) -> bool:
        """Apply the computed differences to PostgreSQL."""
        async with self.pg_pool.acquire() as conn:
            try:
                async with conn.transaction():
                    # First update the global stats
                    await conn.execute(
                        """
                        INSERT INTO global_stats (
                            timestamp,
                            job_requests,
                            job_results,
                            unique_users,
                            unique_dvms,
                            most_popular_kind,
                            most_paid_dvm,
                            total_sats_earned
                        )
                        SELECT 
                            $1 as timestamp,
                            COALESCE(MAX(job_requests), 0) + $2 as job_requests,
                            COALESCE(MAX(job_results), 0) + $3 as job_results,
                            (SELECT COUNT(DISTINCT id) FROM (
                                SELECT id FROM users 
                                UNION 
                                SELECT unnest($4::text[]) as id
                            ) all_users) as unique_users,
                            (SELECT COUNT(DISTINCT id) FROM (
                                SELECT id FROM dvms 
                                UNION 
                                SELECT unnest($5::text[]) as id
                            ) all_dvms) as unique_dvms,
                            CASE 
                                WHEN $6 IS NOT NULL THEN $6 
                                ELSE most_popular_kind 
                            END as most_popular_kind,
                            CASE 
                                WHEN $7 IS NOT NULL THEN $7 
                                ELSE most_paid_dvm 
                            END as most_paid_dvm,
                            COALESCE(MAX(total_sats_earned), 0) + $8 as total_sats_earned
                        FROM global_stats
                    """,
                        datetime.utcnow(),
                        diff.job_requests,
                        diff.job_results,
                        list(diff.new_user_ids),
                        list(diff.new_dvm_ids),
                        max(diff.kind_request_counts.items(), key=lambda x: x[1])[0]
                        if diff.kind_request_counts
                        else None,
                        max(diff.dvm_earnings.items(), key=lambda x: x[1])[0]
                        if diff.dvm_earnings
                        else None,
                        diff.sats_earned,
                    )

                    # Update users table
                    if diff.new_user_ids:
                        await conn.execute(
                            """
                            INSERT INTO users (id, first_seen)
                            SELECT unnest($1::text[]), $2
                            ON CONFLICT (id) DO NOTHING
                        """,
                            list(diff.new_user_ids),
                            datetime.utcnow(),
                        )

                    # Update dvms table
                    if diff.new_dvm_ids:
                        await conn.execute(
                            """
                            INSERT INTO dvms (id, first_seen)
                            SELECT unnest($1::text[]), $2
                            ON CONFLICT (id) DO NOTHING
                        """,
                            list(diff.new_dvm_ids),
                            datetime.utcnow(),
                        )

                    return True

            except Exception as e:
                logger.error(f"Failed to apply diff to postgres: {e}")
                return False

    async def save_events_to_mongo(self, events: List[Dict]) -> bool:
        """Save events to MongoDB, ignoring duplicates."""
        try:
            if events:
                await self.mongo.events.insert_many(events, ordered=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save events to mongo: {e}")
            return False

    async def log_queue_stats(self):
        """Log current queue length and processing stats."""
        try:
            queue_length = self.redis.llen(self.queue_name)
            logger.info(
                f"Queue stats:\n"
                f"  Queue length: {queue_length}\n"
                f"  Processed events: {self.event_count}\n"
                f"  Error count: {self.error_count}"
            )
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")

    async def process_forever(self):
        """Main processing loop."""
        logger.info(
            f"Starting batch processor:\n"
            f"  Queue: {self.queue_name}\n"
            f"  Batch size: {self.batch_size}\n"
            f"  Max wait: {self.max_wait_seconds}s"
        )

        while True:
            try:
                # Get batch of events
                events = await self.get_batch_of_events()

                if events:
                    # Log batch info
                    logger.info(f"Processing batch of {len(events)} events")

                    # 1. Compute diffs (pure computation, no DB access)
                    diff = self.compute_batch_diff(events)

                    # 2. Save events to MongoDB (can be done in parallel with postgres)
                    mongo_task = asyncio.create_task(self.save_events_to_mongo(events))

                    # 3. Apply diffs to PostgreSQL
                    postgres_success = await self.apply_diff_to_postgres(diff)

                    # 4. Wait for MongoDB save to complete
                    mongo_success = await mongo_task

                    if postgres_success and mongo_success:
                        self.event_count += len(events)
                        self.error_count = 0  # Reset error count on success
                    else:
                        self.error_count += 1

                # Log stats periodically
                if self.event_count % 100 == 0:
                    await self.log_queue_stats()

                # Check error threshold
                if self.error_count >= 10:
                    logger.critical("Too many consecutive errors, shutting down...")
                    break

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                logger.error(traceback.format_exc())
                self.error_count += 1

                if self.error_count >= 10:
                    logger.critical("Too many consecutive errors, shutting down...")
                    break

                await asyncio.sleep(1)


async def main():
    """Initialize and run the batch processor."""
    try:
        # Initialize your connections
        pg_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            database=os.getenv("POSTGRES_DB", "dvmdash"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
        )

        mongo_client = motor.motor_asyncio.AsyncIOMotorClient(
            os.getenv("MONGO_URL", "mongodb://localhost:27017")
        )

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        processor = BatchProcessor(
            redis_url=redis_url,
            pg_pool=pg_pool,
            mongo_client=mongo_client,
            batch_size=int(os.getenv("BATCH_SIZE", "100")),
            max_wait_seconds=int(os.getenv("MAX_WAIT_SECONDS", "5")),
        )

        await processor.process_forever()

    except KeyboardInterrupt:
        logger.info("Shutting down batch processor...")
    except Exception as e:
        logger.exception("Fatal error in batch processor")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
