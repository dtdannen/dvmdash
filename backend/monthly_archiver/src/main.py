import os
import sys
import time
import asyncio
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Set, Optional, Tuple
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
from util import RedisLock
import uuid


# custom exception called MultipleMonthBatch
class MultipleMonthBatch(Exception):
    pass


print("Environment variables:")
for key, value in os.environ.items():
    print(f"{key}={value}")

NOSTR_EPOCH = datetime(
    2020, 11, 7, tzinfo=timezone.utc
)  # need a minimum date for DVM activity; apparently this is the day Nostr was first published

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DAYS_TO_KEEP_DATA = 64
DELAY_FOR_FOLLOWERS_TO_UPDATE_MONTH = 15

# Simple logging setup that works well with Docker
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)


class MonthlyArchiver:
    def __init__(
        self,
        redis_url: str,
        metrics_pool: asyncpg.Pool,  # Pool for metrics database
        queue_name: str = "dvmdash_events",
        max_wait_seconds: int = 5,
        backtest_mode: bool = False,
    ):
        self.redis = redis.from_url(redis_url)
        self.metrics_pool = metrics_pool
        self.queue_name = queue_name
        self.max_wait_seconds = max_wait_seconds
        self.event_count = 0
        self.error_count = 0
        self.backtest_mode = backtest_mode
        self.current_year = None
        self.current_month = None
        self.current_day = None  # only the leader uses this, so we dont save to redis
        self.first_day_seen = None  # this is the date of the first event we get

        self.monthly_cleanup_buffer_days = 3

        self.daily_cleanup_time_buffer_has_passed = False
        self.last_daily_cleanup = None

        self.redis_state_key = "dvmdash_state"
        self.redis_monthly_cleanup_lock_key = "dvmdash_monthly_cleanup_lock"

        # set a uuid
        self.unique_id = str(uuid.uuid4())

        logger.info(
            f"Creating Monthly Cleanup {self.unique_id}:\n"
            f" max_wait_seconds={max_wait_seconds},"
            f" backtest_mode={backtest_mode},"
            f" with unique_id={self.unique_id}"
        )

    async def _get_redis_state(self) -> Optional[dict]:
        """Get the current state from Redis.
        Returns None if no state exists.

        Example state:
            current_state = {
                "year": 2024,
                "month": 1,
                "last_monthly_cleanup_completed": "2024-01-01T00:00:00Z",
                "cleanup": {
                    "in_progress": False,
                    "requested": False,
                    "requested_by": None,  # Could store follower ID here
                    "started_at": None,    # Timestamp when backup started
                }
            }

        """
        try:
            state_bytes = await self.redis.get(self.redis_state_key)
            if not state_bytes:
                return None

            # Convert bytes to string, then parse JSON
            state_str = state_bytes.decode("utf-8")
            return json.loads(state_str)

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing Redis state: {e}")
            logger.error(f"{traceback.format_exc()}")
            return None

    async def _set_redis_state(self, state: dict) -> bool:
        """Set the current state in Redis.
        Returns True if successful, False otherwise.
        """
        if not self.validate_state(state):
            logger.error(f"Invalid state structure: {state}")
            return False

        try:
            # Convert dict to JSON string, then encode to bytes
            state_json = json.dumps(state)
            await self.redis.set(self.redis_state_key, state_json)
            return True

        except Exception as e:
            logger.error(f"Error setting Redis state: {e}")
            logger.error(f"{traceback.format_exc()}")
            return False

    def validate_state(self, state: dict) -> bool:
        """Simple validation for state dictionary"""
        try:
            # Basic structure validation
            assert isinstance(state["year"], int) and 2023 <= state["year"] <= 9999
            assert isinstance(state["month"], int) and 1 <= state["month"] <= 12
            assert isinstance(state["last_monthly_cleanup_completed"], datetime)
            assert isinstance(state["cleanup"], dict)
            assert isinstance(state["cleanup"]["in_progress"], bool)
            assert isinstance(state["cleanup"]["requested"], bool)
            # todo add remaining 2 fields here
            return True
        except (KeyError, AssertionError):
            logger.error(f"{traceback.format_exc()}")
            return False

    async def _set_backup_started(self) -> bool:
        """
        Mark backup as started in Redis state.
        Returns True if successfully updated state, False otherwise.
        """
        try:
            current_state = await self._get_redis_state()
            if not current_state:
                logger.error("Could not get current state from Redis")
                return False

            current_state["cleanup"]["in_progress"] = True
            current_state["cleanup"]["started_at"] = datetime.now(
                timezone.utc
            ).isoformat()

            success = await self._set_redis_state(current_state)
            if not success:
                logger.error("Failed to set backup started state in Redis")
                return False

            logger.info("Successfully marked backup as started in Redis state")
            return True

        except Exception as e:
            logger.error(f"Error setting backup started state: {e}")
            return False

    async def _set_backup_completed(self) -> bool:
        """
        Mark backup as completed in Redis state.
        Returns True if successfully updated state, False otherwise.
        """
        try:
            # Get current state
            current_state = await self._get_redis_state()
            if not current_state:
                logger.error("Could not get current state from Redis")
                return False

            # Verify backup was in progress
            if not current_state["cleanup"]["in_progress"]:
                logger.warning(
                    "Attempting to complete backup that wasn't marked as in progress"
                )

            # Reset all backup-related fields
            current_state["cleanup"].update(
                {
                    "in_progress": False,
                    "requested": False,
                    "requested_by": None,
                    "started_at": None,
                }
            )

            # Update the last transition time
            current_state["last_monthly_cleanup_completed"] = datetime.now(
                timezone.utc
            ).isoformat()

            # Save updated state
            success = await self._set_redis_state(current_state)
            if not success:
                logger.error("Failed to set backup completed state in Redis")
                return False

            logger.info("Successfully marked backup as completed in Redis state")
            return True

        except Exception as e:
            logger.error(f"Error setting backup completed state: {e}")
            return False

    async def _check_and_perform_cleanups(
        self, latest_event_of_batch: Optional[datetime]
    ):
        # Only leader does cleanups
        logger.info(
            f"Calling _check_and_perform_cleanups with year={self.current_year} and month={self.current_month}"
        )
        if self.is_leader:
            logger.warning(f"Leader is performing cleanups")

            if latest_event_of_batch and self.daily_cleanup_time_buffer_has_passed:
                logger.info(
                    f"Doing daily cleanup, last cleanup was {self.last_daily_cleanup}, "
                    f"will become {latest_event_of_batch}"
                )
                async with (self.metrics_pool.acquire() as conn):
                    await self._daily_cleanup_of_month_old_data(
                        conn, reference_timestamp=latest_event_of_batch
                    )
                    self.last_daily_cleanup = latest_event_of_batch

            if self.monthly_cleanup_time_buffer_has_passed:
                async with RedisLock(
                    self.redis, "monthly_cleanup_lock", expire_seconds=60
                ) as lock:
                    while self.months_to_clean_up > 0:
                        logger.info(
                            f"Leader is starting monthly cleanup process, current year={self.current_year}, current"
                            f" month={self.current_month} and there are {self.months_to_clean_up}"
                            f" months to cleanup"
                        )
                        year_to_cleanup = self.current_year
                        month_to_cleanup = self.current_month

                        new_year = self.current_year
                        new_month = self.current_month + 1
                        if new_month >= 13:
                            new_year = self.current_year + 1
                            new_month = 1

                        logger.info(
                            f"Old year={self.current_year}, month={self.current_month}"
                        )
                        logger.info(f"New year={new_year}, month={new_month}")

                        # now we need to update redis so all followers get new year and month
                        # once followers update, they will ignore all events from before the new month
                        # which means it will be safe to do the monthly backup
                        await self._set_redis_current_year_month(new_year, new_month)

                        # now we wait to be sure redis was updated
                        redis_year, redis_month = None, None
                        while redis_year != new_year and redis_month != new_month:
                            (
                                redis_year,
                                redis_month,
                            ) = await self._get_redis_current_year_month()
                            await asyncio.sleep(0.2)
                        logger.info(
                            f"Redis successfully updated to use new year ({new_year}) and new month ({new_month})"
                        )

                        self.current_year = redis_year
                        self.current_month = redis_month

                        # batch processor followers should always run fast, ideally processing a batch in under 5 seconds
                        # so therefore if we wait DELAY_FOR_FOLLOWERS_TO_UPDATE_MONTH seconds, all followers should be done
                        logger.info(
                            f"Leader is now waiting for followers to finish any current "
                            f"processing, sleeping {DELAY_FOR_FOLLOWERS_TO_UPDATE_MONTH}s"
                        )
                        await asyncio.sleep(DELAY_FOR_FOLLOWERS_TO_UPDATE_MONTH)

                        # now we can safely perform the monthly cleanup
                        async with (self.metrics_pool.acquire() as conn):
                            logger.debug(
                                f"Calling monthly cleanup with year={year_to_cleanup}, month={month_to_cleanup}"
                            )
                            await self._monthly_cleanup(
                                conn, year_to_cleanup, month_to_cleanup
                            )
                        logger.info(f"Successfully performed monthly cleanup")

                        self.months_to_clean_up -= 1

                    self.monthly_cleanup_time_buffer_has_passed = False

        else:
            logger.error(
                f"Somehow follower {self.unique_id} is trying to perform a cleanup, doing nothing..."
            )

    async def _daily_cleanup_of_month_old_data(
        self, conn: asyncpg.Connection, reference_timestamp: Optional[datetime] = None
    ) -> None:
        """
        IMPORTANT: While this is run daily, it only affects entities older than DAYS_TO_KEEP_DATA days

        Performs daily cleanup tasks:
        1. Two-phase entity cleanup (mark inactive, delete old inactive)
        2. Maintain 35-day rolling window for entity_activity
        """
        try:
            batch_size = 1000
            current_time = reference_timestamp or datetime.now(timezone.utc)
            cutoff_date = current_time - timedelta(days=DAYS_TO_KEEP_DATA)
            logger.info(
                f"Starting daily cleanup process at {current_time.strftime('%Y-%m-%d %H:%M:%S UTC')} - "
                f"removing events older than {cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

            while True:
                # First get the IDs of DVMs to update
                inactive_ids = await conn.fetch(
                    """
                    SELECT id 
                    FROM dvms
                    WHERE last_seen < COALESCE($2, CURRENT_TIMESTAMP) - INTERVAL '64 days'
                    AND is_active = TRUE
                    LIMIT $1
                    FOR UPDATE SKIP LOCKED
                    """,
                    batch_size,
                    reference_timestamp,
                )

                if not inactive_ids:
                    break

                # Then update those specific DVMs
                updated_count = await conn.execute(
                    """
                    UPDATE dvms 
                    SET is_active = FALSE,
                        deactivated_at = COALESCE($2, CURRENT_TIMESTAMP)
                    WHERE id = ANY($1)
                    """,
                    [row["id"] for row in inactive_ids],
                    reference_timestamp,
                )

                if not updated_count or updated_count == "0":
                    break

                await asyncio.sleep(0.0001)  # prevent tight loop

            # Phase 2: Delete entities inactive for 60+ days and log them
            deleted_dvms = await conn.fetch(
                """
                WITH deleted AS (
                    DELETE FROM dvms
                    WHERE last_seen < COALESCE($1, CURRENT_TIMESTAMP) - INTERVAL '64 days'
                    AND is_active = FALSE
                    RETURNING id, first_seen, last_seen, deactivated_at
                )
                INSERT INTO cleanup_log (
                    entity_id,
                    entity_type,
                    first_seen,
                    last_seen,
                    deactivated_at,
                    deleted_at
                )
                SELECT 
                    id,
                    'dvm',
                    first_seen,
                    last_seen,
                    deactivated_at,
                    COALESCE($1, CURRENT_TIMESTAMP)
                FROM deleted
                RETURNING entity_id
                """,
                reference_timestamp,
            )

            logger.info(f"Deleted {len(deleted_dvms)} inactive DVMs")

            # Clean up old activity data (keep exactly DAYS_TO_KEEP_DATA days)
            deleted_activities = await conn.fetchval(
                """
                WITH deleted AS (
                    DELETE FROM entity_activity
                    WHERE observed_at < COALESCE($1, CURRENT_TIMESTAMP) - INTERVAL '64 days'
                    RETURNING id
                )
                SELECT COUNT(*) FROM deleted
                """,
                reference_timestamp,
            )

            logger.info(f"Removed {deleted_activities} old activity records")

            deleted_raw_events = await conn.fetchval(
                """
                WITH deleted AS (
                    DELETE FROM raw_events
                    WHERE created_at < COALESCE($1, CURRENT_TIMESTAMP) - INTERVAL '64 days'
                    RETURNING id
                )
                SELECT COUNT(*) FROM deleted
                """,
                reference_timestamp,
            )

            logger.info(f"Removed {deleted_raw_events} old raw events")

        except Exception as e:
            logger.error(f"Error during daily cleanup: {e}")
            logger.error(traceback.format_exc())
            raise

    async def _monthly_cleanup(self, conn: asyncpg.Connection, year, month) -> None:
        """Performs monthly cleanup tasks with accurate month boundary handling."""
        try:
            logger.info("Starting monthly cleanup process...")

            # Get the previous month's start and end
            month_start = datetime(
                year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            month_end = month_start + relativedelta(months=1)

            logger.debug(f"month_start={month_start}")
            logger.debug(f"month_end={month_end}")

            # Format year_month string in YYYY-MM format
            year_month = month_start.strftime("%Y-%m")
            logger.debug(f"year_month = {year_month}")
            await conn.execute(
                """
                INSERT INTO monthly_activity (
                    year_month,
                    total_requests,
                    total_responses,
                    unique_dvms,
                    unique_kinds,
                    unique_users,
                    dvm_activity,
                    kind_activity
                )
                WITH period_metrics AS (
                    SELECT
                        COUNT(*) FILTER (
                            WHERE entity_type = 'kind' 
                            AND CAST(entity_id AS INTEGER) BETWEEN 5000 AND 5999
                        ) as total_requests,
                        COUNT(*) FILTER (
                            WHERE entity_type = 'kind' 
                            AND CAST(entity_id AS INTEGER) BETWEEN 6000 AND 6999
                        ) as total_responses,
                        COUNT(DISTINCT entity_id) FILTER (WHERE entity_type = 'dvm') as unique_dvms,
                        COUNT(DISTINCT entity_id) FILTER (
                            WHERE entity_type = 'kind' AND 
                            CAST(entity_id AS INTEGER) BETWEEN 5000 AND 5999
                        ) as unique_kinds,
                        COUNT(DISTINCT entity_id) FILTER (WHERE entity_type = 'user') as unique_users
                    FROM entity_activity
                    WHERE observed_at >= $1 AND observed_at < $2
                ),
                monthly_dvm_stats AS (
                    SELECT 
                        dvm_id,
                        SUM(period_feedback) as feedback_count,
                        SUM(period_responses) as response_count
                    FROM dvm_stats_rollups
                    WHERE period_start >= $1 AND period_end < $2
                    GROUP BY dvm_id
                ),
                monthly_kind_stats AS (
                    SELECT 
                        kind,
                        SUM(period_requests) as request_count,
                        SUM(period_responses) as response_count
                    FROM kind_stats_rollups
                    WHERE period_start >= $1 AND period_end < $2
                    GROUP BY kind
                )
                SELECT
                    $3::text as year_month,
                    COALESCE(pm.total_requests, 0) as total_requests,
                    COALESCE(pm.total_responses, 0) as total_responses,
                    COALESCE(pm.unique_dvms, 0) as unique_dvms,
                    COALESCE(pm.unique_kinds, 0) as unique_kinds,
                    COALESCE(pm.unique_users, 0) as unique_users,
                    COALESCE(
                        (SELECT jsonb_agg(row_to_json(d)) 
                         FROM monthly_dvm_stats d),
                        '[]'::jsonb
                    ) as dvm_activity,
                    COALESCE(
                        (SELECT jsonb_agg(row_to_json(k)) 
                         FROM monthly_kind_stats k),
                        '[]'::jsonb
                    ) as kind_activity
                FROM period_metrics pm
                """,
                month_start,
                month_end,
                year_month,
            )

            # Clean up old logs
            deleted_logs = await conn.fetchval(
                """
                WITH deleted AS (
                    DELETE FROM cleanup_log
                    WHERE deleted_at < COALESCE($1, CURRENT_TIMESTAMP) - INTERVAL '1 year'
                    RETURNING id
                )
                SELECT COUNT(*) FROM deleted
                """,
                month_start,
            )

            logger.info(f"Removed {deleted_logs} old cleanup logs")
            logger.info(
                f"Monthly cleanup process for {year_month} completed successfully"
            )

        except Exception as e:
            logger.error(f"Error during monthly cleanup: {e}")
            logger.error(traceback.format_exc())
            raise

        # Get interval from env var, default 24 hours in production, can be seconds for testing
        daily_cleanup_interval = int(
            os.getenv("DAILY_CLEANUP_INTERVAL_SECONDS", 24 * 60 * 60)
        )
        logger.info(f"Daily cleanup will run every {daily_cleanup_interval} seconds")

    async def process_forever(self):
        consecutive_errors = 0
        last_health_check = time.time()
        last_daily_cleanup = time.time()

        # Get interval from env var, default 24 hours in production, can be seconds for testing
        daily_cleanup_interval = int(
            os.getenv("DAILY_CLEANUP_INTERVAL_SECONDS", 24 * 60 * 60)
        )
        logger.info(f"Daily cleanup will run every {daily_cleanup_interval} seconds")

        while True:
            try:
                # 1. Check redis state for backup requests
                current_state = await self._get_redis_state()
                if current_state and current_state["cleanup"]["requested"]:
                    logger.info(
                        f"Backup requested by {current_state['cleanup']['requested_by']}, acquiring lock..."
                    )

                    try:
                        async with RedisLock(
                            self.redis,
                            self.redis_monthly_cleanup_lock_key,
                            expire_seconds=300,
                        ) as single_attempt_lock:
                            # Double check state after getting lock
                            current_state = await self._get_redis_state()
                            if current_state["cleanup"]["requested"]:
                                # Set backup started
                                await self._set_backup_started()

                                logger.info(
                                    f"Monthly archiver is now waiting 15 seconds for batch processors to finish"
                                    f"up any processing they are in the middle of running"
                                )
                                await asyncio.sleep(
                                    os.getenv(
                                        "BATCH_PROCESSOR_GRACE_PERIOD_BEFORE_UPDATE_SECONDS",
                                        15,
                                    )
                                )

                                # Do the monthly backup
                                async with self.metrics_pool.acquire() as conn:
                                    await self._monthly_cleanup(
                                        conn,
                                        current_state["year"],
                                        current_state["month"],
                                    )

                                # Update to next month/year
                                new_month = current_state["month"] + 1
                                new_year = current_state["year"]
                                if new_month > 12:
                                    new_month = 1
                                    new_year += 1

                                # Update state
                                current_state.update(
                                    {
                                        "year": new_year,
                                        "month": new_month,
                                        "cleanup": {
                                            "in_progress": False,
                                            "requested": False,
                                            "requested_by": None,
                                            "started_at": None,
                                        },
                                    }
                                )
                                await self._set_redis_state(current_state)

                                logger.info(
                                    f"Monthly backup complete, moved to {new_year}-{new_month}"
                                )

                    except TimeoutError:
                        logger.warning(
                            "Could not acquire lock for backup, will retry next cycle"
                        )

                # 2. Check if it's time for daily cleanup
                if time.time() - last_daily_cleanup >= daily_cleanup_interval:
                    logger.info("Starting daily cleanup...")
                    async with self.metrics_pool.acquire() as conn:
                        await self._daily_cleanup_of_month_old_data(conn)
                    last_daily_cleanup = time.time()
                    logger.info("Daily cleanup complete")

                # Health check logging
                if time.time() - last_health_check >= 60:
                    logger.info(f"Health check - Archiver running normally")
                    last_health_check = time.time()

                # Small sleep to prevent tight loop
                await asyncio.sleep(1)
                consecutive_errors = 0

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                logger.error(traceback.format_exc())
                consecutive_errors += 1

                if consecutive_errors >= 10:
                    logger.critical(
                        "Too many consecutive errors (10+), shutting down for safety..."
                    )
                    return

                # Exponential backoff on errors
                await asyncio.sleep(min(30, 2**consecutive_errors))


async def main():
    """Initialize and run the batch processor."""
    logger.info("Starting monthly archiver...")

    try:
        # Initialize metrics database connection pool
        logger.info("Connecting to metrics database...")
        metrics_pool = await asyncpg.create_pool(
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            database=os.getenv("POSTGRES_DB", "dvmdash"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", 5432),
            min_size=5,
            max_size=20,
        )

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        logger.info(f"Connecting to Redis at {redis_url}")

        monthly_archiver = MonthlyArchiver(
            redis_url=redis_url,
            metrics_pool=metrics_pool,
            max_wait_seconds=int(os.getenv("MAX_WAIT_SECONDS", "5")),
            backtest_mode=os.getenv("BACKTEST_MODE", "false").lower() == "true",
        )

        await monthly_archiver.process_forever()

    except KeyboardInterrupt:
        logger.info("Received shutdown signal, cleaning up...")
    except Exception as e:
        logger.exception("Fatal error in batch processor")
        sys.exit(1)
    finally:
        logger.info("Closing database connections...")
        if "metrics_pool" in locals():
            await metrics_pool.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
