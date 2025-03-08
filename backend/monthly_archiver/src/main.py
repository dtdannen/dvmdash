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
from util import ArchiverRedisLock
import uuid

# Import the new coordinator components
from coordinator import CoordinatorManager


# custom exception called MultipleMonthBatch
class MultipleMonthBatch(Exception):
    pass


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
    ):
        logger.info(f"Initializing Redis with URL: {redis_url}")
        self.redis = redis.from_url(redis_url)
        logger.info(f"Redis client initialized: {self.redis}")
        self.metrics_pool = metrics_pool
        self.queue_name = queue_name
        self.event_count = 0
        self.error_count = 0
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
            f"Creating Monthly Archiver {self.unique_id}:\n"
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
            state_bytes = self.redis.get(self.redis_state_key)
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
            self.redis.set(self.redis_state_key, state_json)
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

    async def _set_backup_completed(self, new_year, new_month) -> bool:
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

            # double check next month and year make sense
            valid_new_month_year = False
            if new_year == current_state["year"]:
                if (
                    current_state["month"] < 12
                    and new_month == current_state["month"] + 1
                ):
                    valid_new_month_year = True
            else:
                if (
                    new_year == current_state["year"] + 1
                    and current_state["month"] == 12
                    and new_month == 1
                ):
                    valid_new_month_year = True

            if not valid_new_month_year:
                logger.error(
                    f"Before finishing monthly backup and writing to redist state, new year and month don't"
                    f" match"
                )
                logger.error(
                    f"Previous year month was {current_state['year']}/{current_state['month']} and "
                    f"new year month is {new_year}/{new_month}"
                )
                return False

            current_state["year"] = new_year
            current_state["month"] = new_month

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
                            WHERE kind BETWEEN 5000 AND 5999
                        ) as total_requests,
                        COUNT(*) FILTER (
                            WHERE kind BETWEEN 6000 AND 6999
                        ) as total_responses,
                        COUNT(DISTINCT entity_id) FILTER (WHERE entity_type = 'dvm') as unique_dvms,
                        COUNT(DISTINCT kind) FILTER (
                            WHERE kind BETWEEN 5000 AND 5999
                        ) as unique_kinds,
                        COUNT(DISTINCT entity_id) FILTER (WHERE entity_type = 'user') as unique_users
                    FROM entity_activity
                    WHERE observed_at >= $1 AND observed_at < $2
                ),
                monthly_dvm_stats AS (
                    SELECT 
                        entity_id as dvm_id,
                        COUNT(DISTINCT CASE 
                            WHEN event_id LIKE 'feed%' THEN event_id
                        END) as feedback_count,
                        COUNT(DISTINCT CASE 
                            WHEN event_id LIKE 'resp%' THEN event_id
                        END) as response_count
                    FROM entity_activity
                    WHERE entity_type = 'dvm'
                    AND observed_at >= $1 AND observed_at < $2
                    GROUP BY entity_id
                ),
                monthly_kind_stats AS (
                    SELECT 
                        kind,
                        COUNT(DISTINCT CASE 
                            WHEN kind BETWEEN 5000 AND 5999 
                            THEN event_id 
                        END) as request_count,
                        COUNT(DISTINCT CASE 
                            WHEN kind BETWEEN 6000 AND 6999 
                            THEN event_id
                        END) as response_count
                    FROM entity_activity
                    WHERE kind IS NOT NULL
                    AND observed_at >= $1 AND observed_at < $2
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
                        with ArchiverRedisLock(
                            self.redis,
                            self.redis_monthly_cleanup_lock_key,
                            expire_seconds=300,
                            retry_times=3,
                            retry_delay=1.0,
                        ) as multi_attempt_lock:
                            # Double check state after getting lock
                            current_state = await self._get_redis_state()
                            if current_state["cleanup"]["requested"]:
                                # Set backup started
                                await self._set_backup_started()

                                logger.info(
                                    f"Monthly archiver is now waiting 15 seconds for batch processors to finish"
                                    f"up any processing they are in the middle of running"
                                )
                                grace_period = int(
                                    os.getenv(
                                        "BATCH_PROCESSOR_GRACE_PERIOD_BEFORE_UPDATE_SECONDS",
                                        15,
                                    )
                                )

                                # Update to next month/year
                                new_month = current_state["month"] + 1
                                new_year = current_state["year"]
                                if new_month > 12:
                                    new_month = 1
                                    new_year += 1

                                for i in range(grace_period):
                                    await asyncio.sleep(1)
                                    logger.info(
                                        f"Archiver will perform monthly backup in {grace_period-i}s, moving"
                                        f" from {current_state['year']}/{current_state['month']} to"
                                        f" {new_year}/{new_month}"
                                    )

                                # Do the monthly backup
                                async with self.metrics_pool.acquire() as conn:
                                    await self._monthly_cleanup(
                                        conn,
                                        current_state["year"],
                                        current_state["month"],
                                    )

                                save_to_redis_success = (
                                    await self._set_backup_completed(
                                        new_year, new_month
                                    )
                                )
                                if save_to_redis_success:
                                    logger.success(
                                        f"Monthly backup complete, moved to {new_year}-{new_month}"
                                    )
                                else:
                                    # TODO - consider retry logic here...
                                    logger.error(
                                        f"Monthly backup seemed to go through but saving to redis failed..."
                                    )

                    except TimeoutError:
                        logger.warning(
                            "Could not acquire lock for backup, will retry next cycle"
                        )

                # 2. Check if it's time for daily cleanup
                # if time.time() - last_daily_cleanup >= daily_cleanup_interval:
                #     logger.info("Starting daily cleanup...")
                #     async with self.metrics_pool.acquire() as conn:
                #         await self._daily_cleanup_of_month_old_data(conn)
                #     last_daily_cleanup = time.time()
                #     logger.info("Daily cleanup complete")

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


class SystemCoordinator:
    """
    Main system coordinator that manages both the monthly archiver and the general coordinator.
    This class is responsible for running both components in parallel.
    """
    
    def __init__(self, redis_url: str, metrics_pool: asyncpg.Pool):
        self.redis_url = redis_url
        self.metrics_pool = metrics_pool
        self.redis = redis.from_url(redis_url)
        
        # Initialize both components
        self.monthly_archiver = MonthlyArchiver(
            redis_url=redis_url,
            metrics_pool=metrics_pool,
        )
        
        self.coordinator = CoordinatorManager(
            redis_client=self.redis,
            metrics_pool=metrics_pool,
        )
        
        logger.info("System Coordinator initialized with both archiver and coordinator components")
    
    async def run(self):
        """Run both the monthly archiver and the coordinator in parallel"""
        try:
            # Create tasks for both components
            archiver_task = asyncio.create_task(
                self.monthly_archiver.process_forever(),
                name="monthly_archiver"
            )
            
            coordinator_task = asyncio.create_task(
                self.coordinator.process_forever(),
                name="coordinator"
            )
            
            logger.info("Started both archiver and coordinator tasks")
            
            # Wait for both tasks to complete (they should run forever)
            await asyncio.gather(archiver_task, coordinator_task)
            
        except asyncio.CancelledError:
            logger.info("System Coordinator received cancellation request")
            raise
        except Exception as e:
            logger.error(f"Error in System Coordinator: {e}")
            logger.error(traceback.format_exc())
            raise


async def main():
    """Initialize and run the system coordinator."""
    logger.info("Starting system coordinator (monthly archiver + relay coordinator)...")

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

        # Create and run the system coordinator
        system_coordinator = SystemCoordinator(
            redis_url=redis_url,
            metrics_pool=metrics_pool,
        )
        
        await system_coordinator.run()

    except KeyboardInterrupt:
        logger.info("Received shutdown signal, cleaning up...")
    except Exception as e:
        logger.exception("Fatal error in system coordinator")
        sys.exit(1)
    finally:
        logger.info("Closing database connections...")
        if "metrics_pool" in locals():
            await metrics_pool.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
