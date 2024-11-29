import os
import sys
import time
import asyncio
from datetime import datetime
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from collections import defaultdict
import asyncpg
import redis
import json
import base64
import traceback
from loguru import logger
import redis
from redis import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

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
    new_user_ids: Set[str] = None
    new_dvm_ids: Set[str] = None
    new_kind_ids: Set[int] = None
    kind_request_counts: Dict[int, int] = None

    def __post_init__(self):
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
        metrics_pool: asyncpg.Pool,  # Pool for metrics database
        events_pool: asyncpg.Pool,  # Pool for events database
        queue_name: str = "dvmdash_events",
        batch_size: int = 100,
        max_wait_seconds: int = 5,
    ):
        self.redis = redis.from_url(redis_url)
        self.metrics_pool = metrics_pool
        self.events_pool = events_pool
        self.queue_name = queue_name
        self.batch_size = batch_size
        self.max_wait_seconds = max_wait_seconds
        self.event_count = 0
        self.error_count = 0

    def extract_nostr_event(self, message: bytes) -> Dict:
        """Extract the Nostr event from Redis message."""
        try:
            # Now message is just the JSON string directly
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            event_data = json.loads(message)

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
            event_id = event.get("id")

            if not kind or not pubkey or not event_id:
                if event_id:
                    logger.warning(f"Event missing kind or pubkey: {event_id}")
                else:
                    logger.warning(f"Event missing event id")
                continue

            if 5000 <= kind < 6000:  # Job requests
                diff.job_requests += 1
                diff.new_user_ids.add(pubkey)
                diff.new_kind_ids.add(kind)
                diff.kind_request_counts[kind] += 1

            elif 6000 <= kind < 7000:  # Job results
                diff.job_results += 1
                diff.new_dvm_ids.add(pubkey)

                # TODO see about calculating sats earned
                #  might need a clever solution

        return diff

    async def apply_diff_to_postgres(self, diff: MetricsDiff) -> bool:
        async with self.pg_pool.acquire() as conn:
            try:
                async with conn.transaction():
                    # First get the current stats
                    current_stats = await conn.fetchrow(
                        """
                        SELECT 
                            job_requests, 
                            job_results,
                            total_sats_earned,
                            most_popular_kind,
                            most_paid_dvm
                        FROM global_stats 
                        ORDER BY timestamp DESC 
                        LIMIT 1
                    """
                    )

                    # Then insert new row with updated totals
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
                        ) VALUES ($1, $2, $3, 
                            (SELECT COUNT(DISTINCT id) FROM (
                                SELECT id FROM users 
                                UNION 
                                SELECT unnest($4::text[]) as id
                            ) all_users),
                            (SELECT COUNT(DISTINCT id) FROM (
                                SELECT id FROM dvms 
                                UNION 
                                SELECT unnest($5::text[]) as id
                            ) all_dvms),
                            $6, $7, $8)
                    """,
                        datetime.utcnow(),
                        (current_stats["job_requests"] or 0) + diff.job_requests,
                        (current_stats["job_results"] or 0) + diff.job_results,
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

    async def save_events_to_postgres(self, events: List[Dict]) -> bool:
        """Save raw events to the events PostgreSQL database."""
        try:
            if not events:
                return True

            async with self.events_pool.acquire() as conn:
                # Prepare values for bulk insert
                values = []
                for event in events:
                    values.append(
                        (
                            event.get("id"),
                            event.get("pubkey"),
                            datetime.fromtimestamp(event.get("created_at", 0)),
                            event.get("kind"),
                            event.get("content"),
                            event.get("sig"),
                            json.dumps(event.get("tags", [])),  # Store tags as JSONB
                            json.dumps(event),  # Store complete event as JSONB
                        )
                    )

                # Use execute_many for efficient bulk insert
                await conn.executemany(
                    """
                    INSERT INTO raw_events (
                        id, pubkey, created_at, kind, content, sig, tags, raw_data
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (id) DO NOTHING
                """,
                    values,
                )

                return True

        except Exception as e:
            logger.error(f"Failed to save events to postgres: {e}")
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    def format_metrics_row(timestamp, diff_metrics, total_metrics, queue_length):
        """Format metrics as a table row."""
        return (
            f"{timestamp} | "
            f"Queue: {queue_length:>5} | "  # Added queue length
            f"Δjobs: {diff_metrics['job_requests']:>4}/{diff_metrics['job_results']:<4} | "
            f"Δsats: {diff_metrics['sats_earned']:>8,} | "
            f"Δusers: {diff_metrics['new_users']:>4} | "
            f"ΔDVMs: {diff_metrics['new_dvms']:>3} | "
            f"Tot jobs: {total_metrics['job_requests']:>6,}/{total_metrics['job_results']:<6,} | "
            f"Tot sats: {total_metrics['total_sats_earned']:>10,} | "
            f"Tot users: {total_metrics['unique_users']:>5,} | "
            f"Tot DVMs: {total_metrics['unique_dvms']:>4,}"
        )

    async def process_forever(self):
        header = "Timestamp            | Queue  | Δjobs req/res | Δsats      | Δusers | ΔDVMs | Tot jobs req/res   | Tot sats      | Tot users | DVMs"
        logger.info("\n" + "=" * len(header))
        logger.info(header)
        logger.info("=" * len(header))

        while True:
            try:
                # Get queue length before processing batch
                queue_length = self.redis.llen(self.queue_name)

                events = await self.get_batch_of_events()

                if events:
                    # 1. Compute diffs
                    diff = self.compute_batch_diff(events)

                    # 2. Save events to events database
                    events_task = asyncio.create_task(
                        self.save_events_to_postgres(events)
                    )

                    # 3. Apply diffs to metrics database
                    metrics_success = await self.apply_diff_to_postgres(diff)

                #     # Get new totals and log the row
                #     if metrics_success:
                #         async with self.metrics_pool.acquire() as conn:
                #             global_stats = await conn.fetchrow(
                #                 """
                #                 SELECT
                #                     job_requests,
                #                     job_results,
                #                     unique_users,
                #                     unique_dvms,
                #                     total_sats_earned,
                #                     most_popular_dvm,
                #                     most_paid_dvm,
                #                     most_popular_kind,
                #                     most_paid_kind
                #                 FROM global_stats
                #                 ORDER BY timestamp DESC
                #                 LIMIT 1
                #             """
                #             )
                #
                #             if global_stats:
                #                 diff_metrics = {
                #                     "job_requests": diff.job_requests,
                #                     "job_results": diff.job_results,
                #                     "sats_earned": diff.sats_earned,
                #                     "new_users": len(diff.new_user_ids),
                #                     "new_dvms": len(diff.new_dvm_ids),
                #                 }
                #
                #                 timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                #                 logger.info(
                #                     BatchProcessor.format_metrics_row(
                #                         timestamp,
                #                         diff_metrics,
                #                         global_stats,
                #                         queue_length,
                #                     )
                #                 )
                #
                #     # 4. Wait for events save to complete
                #     events_success = await events_task
                #
                #     if metrics_success and events_success:
                #         self.event_count += len(events)
                #         self.error_count = 0  # Reset error count on success
                #     else:
                #         self.error_count += 1
                #
                # # Check error threshold
                # if self.error_count >= 10:
                #     logger.error("Too many consecutive errors, shutting down...")
                #     break

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                logger.error(traceback.format_exc())
                self.error_count += 1

                if self.error_count >= 10:
                    logger.error("Too many consecutive errors, shutting down...")
                    break

                await asyncio.sleep(1)


async def main():
    """Initialize and run the batch processor."""
    try:
        # Initialize metrics database connection pool
        metrics_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            database=os.getenv("POSTGRES_DB", "dvmdash"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
        )

        # Initialize events database connection pool
        events_pool = await asyncpg.create_pool(
            user=os.getenv("EVENTS_POSTGRES_USER", "postgres"),
            password=os.getenv("EVENTS_POSTGRES_PASSWORD", "postgres"),
            database=os.getenv("EVENTS_POSTGRES_DB", "dvmdash_events"),
            host=os.getenv("EVENTS_POSTGRES_HOST", "localhost"),
        )

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        processor = BatchProcessor(
            redis_url=redis_url,
            metrics_pool=metrics_pool,
            events_pool=events_pool,
            batch_size=int(os.getenv("BATCH_SIZE", "100")),
            max_wait_seconds=int(os.getenv("MAX_WAIT_SECONDS", "5")),
        )

        await processor.process_forever()

    except KeyboardInterrupt:
        logger.info("Shutting down batch processor...")
    except Exception as e:
        logger.exception("Fatal error in batch processor")
        sys.exit(1)
    finally:
        # Clean up connection pools
        if "metrics_pool" in locals():
            await metrics_pool.close()
        if "events_pool" in locals():
            await events_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
