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
from util import BatchProcessorRedisLock
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


@dataclass
class BatchStats:
    period_start: datetime
    period_end: datetime
    period_requests: int = 0
    period_responses: int = 0
    period_feedback: int = 0

    # Track DVMs and their activities
    dvm_responses: Dict[str, int] = None  # dvm -> count of responses
    dvm_feedback: Dict[str, int] = None  # dvm -> count of feedback
    dvm_timestamps: Dict[
        str, datetime
    ] = None  # dvm -> latest timestamp (for last_seen updates)
    dvm_kinds: Dict[str, Set[int]] = None  # dvm -> set of kinds supported

    # Track all entity observations with timestamps
    # entity_id is either a kind or npub (user or dvm)
    entity_activity: Dict[
        str, List[Tuple[str, datetime, str]]
    ] = None  # entity_type -> List[(entity_id, timestamp, event_id)]

    # Track users and their activities
    user_timestamps: Dict[str, datetime] = None  # user -> latest timestamp
    user_is_dvm: Dict[str, bool] = None  # user -> is_dvm flag

    # Track per-kind stats
    kind_requests: Dict[int, int] = None  # kind -> count of requests
    kind_responses: Dict[int, int] = None  # kind -> count of responses

    events_processed: List[Dict] = None

    def __post_init__(self):
        self.dvm_responses = defaultdict(int)
        self.dvm_feedback = defaultdict(int)
        self.dvm_timestamps = defaultdict(
            lambda: datetime.min.replace(tzinfo=timezone.utc)
        )
        self.dvm_kinds = defaultdict(set)
        self.entity_activity = {  # Initialize with empty lists for each entity type
            "dvm": [],
            "user": [],
            "kind": [],
        }
        self.user_timestamps = defaultdict(
            lambda: datetime.min.replace(tzinfo=timezone.utc)
        )
        self.user_is_dvm = defaultdict(bool)
        self.kind_requests = defaultdict(int)
        self.kind_responses = defaultdict(int)
        self.events_processed = []


class BatchProcessor:
    def __init__(
        self,
        redis_url: str,
        metrics_pool: asyncpg.Pool,  # Pool for metrics database
        queue_name: str = "dvmdash_events",
        batch_size: int = 100,
        max_wait_seconds: int = 5,
        backtest_mode: bool = False,
    ):
        self.redis = redis.from_url(redis_url)
        self.metrics_pool = metrics_pool
        self.queue_name = queue_name
        self.batch_size = batch_size
        self.max_wait_seconds = max_wait_seconds
        self.event_count = 0
        self.error_count = 0
        self.backtest_mode = backtest_mode
        self.first_day_seen = None  # this is the date of the first event we get

        self.monthly_cleanup_buffer_days = int(
            os.getenv("MONTHLY_CLEANUP_BUFFER_DAYS", 3)
        )

        self.redis_state_key = "dvmdash_state"
        self.redis_monthly_cleanup_lock_key = "dvmdash_monthly_cleanup_lock"

        # set a uuid
        self.unique_id = str(uuid.uuid4())

        logger.info(
            f"Creating Batch Processor with settings:\n"
            f" batch_size={batch_size},"
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

    async def _request_monthly_backup(self):
        try:
            with BatchProcessorRedisLock(
                self.redis, self.redis_monthly_cleanup_lock_key, expire_seconds=15
            ) as one_time_attempt_lock:
                logger.info(f"Lock acquired, requesting monthly backup...")

                # get the current state, if backup is in progress, just exit early, we got what we wanted
                current_state = await self._get_redis_state()
                if (
                    current_state
                    and current_state["cleanup"]["in_progress"]
                    or current_state["cleanup"]["requested"]
                ):
                    logger.info(
                        f"Exiting early from attempting to request monthly backup, monthly backup"
                        f" already in progress or has been requested"
                    )
                    return True

                # now request monthly backup
                current_state["cleanup"]["requested"] = True
                current_state["cleanup"]["requested_by"] = self.unique_id
                success = await self._set_redis_state(current_state)
                if not success:
                    logger.error(f"Failed to request monthly backup")
                    return False
                logger.success(
                    f"Follower {self.unique_id} successfully requested monthly backup"
                )
                return True
        except TimeoutError:
            logger.error("Could not acquire lock")

        return False

    async def process_events(self, events: List[dict]) -> None:
        """Process a batch of events and update all necessary tables atomically."""
        if not events:
            return

        logger.info(f"Processing {len(events)} events")

        try:
            stats = await self._analyze_events(events)
            if len(stats.events_processed) > 0:
                await self._compute_metrics(stats, events)
            else:
                logger.warning(
                    f"Analyze events did not process any events from this batch"
                )
        except MultipleMonthBatch as e:
            events_per_month = {}
            for event in events:
                timestamp = datetime.fromtimestamp(event["created_at"], tz=timezone.utc)
                year_month_i = (timestamp.year, timestamp.month)

                if year_month_i not in events_per_month:
                    logger.debug(
                        f"Processing events for year/month {year_month_i[0]}/{year_month_i[1]}"
                    )
                    events_per_month[year_month_i] = [event]
                else:
                    events_per_month[year_month_i].append(event)

            logger.warning(
                f"There are {len(events_per_month)} unique year/months in current batch"
            )
            for (year_i, month_i), events in events_per_month.items():
                logger.warning(f"\tyear/month {year_i}/{month_i}: {len(events)} events")

            redis_state = await self._get_redis_state()
            redis_year_month = (redis_state["year"], redis_state["month"])
            redis_year, redis_month = redis_year_month

            for year_month_i in sorted(events_per_month.keys()):
                year_i, month_i = year_month_i
                logger.warning(
                    f"Processing {year_i}/{month_i} with {len(events_per_month[year_month_i])} events and "
                    f"redis current state is {redis_year}/{redis_month}"
                )

                skip_month = False
                while True:
                    if year_month_i == redis_year_month:
                        # year month matches redis, good to go
                        logger.success(
                            f"year/month {year_i}/{month_i} matches redis {redis_year}/{redis_month}, analyzing now..."
                        )
                        break
                    elif redis_year == year_i and redis_month == month_i - 1:
                        # redis is only 1 month behind year_month_i, good to go
                        logger.success(
                            f"year/month {year_i}/{month_i} is 1 month ahead of "
                            f"redis {redis_year}/{redis_month}, analyzing now..."
                        )
                        break
                    elif (
                        redis_year == year_i - 1 and redis_month == 12 and month_i == 1
                    ):
                        # new year scenario when redis is only 1 month behind, good to go
                        logger.success(
                            f"year/month {year_i}/{month_i} is a new year, and is exactly 1 month ahead"
                            f" of redis {redis_year}/{redis_month}, analyzing now..."
                        )
                        break
                    else:
                        if year_i < redis_year:
                            logger.error(
                                f"year/month {year_i}/{month_i} is in the past compared to "
                                f"redis {redis_year}]{redis_month}, ignoring this batch unfortunately"
                            )
                            skip_month = True
                            break
                        elif year_i == redis_year and month_i < redis_month:
                            logger.error(
                                f"year/month {year_i}/{month_i} is in the past compared to "
                                f"redis {redis_year}]{redis_month}, ignoring this batch unfortunately"
                            )
                            skip_month = True
                            break
                        else:
                            # all we need to do is wait, because it's farther in the future
                            logger.info(
                                f"year/month {year_i}/{month_i} is in the future compared to redis "
                                f"{redis_year}/{redis_month}, waiting for monthly cleanup to move us forward..."
                            )

                            need_to_request_backup = True
                            if (
                                redis_state["cleanup"]["requested"]
                                or redis_state["cleanup"]["in_progress"]
                            ):
                                need_to_request_backup = False

                            if need_to_request_backup:
                                await self._request_monthly_backup()

                    await asyncio.sleep(0.5)
                    redis_state = await self._get_redis_state()
                    redis_year_month = (redis_state["year"], redis_state["month"])
                    redis_year, redis_month = redis_year_month

                if skip_month:
                    continue

                # if we reach here, we are good to proceed
                stats_i = await self._analyze_events(events_per_month[year_month_i])

                if len(stats_i.events_processed) > 0:
                    logger.warning(
                        f"Last event of stats batch has timestamp of {stats_i.period_end}"
                    )
                    await self._compute_metrics(stats_i, events_per_month[year_month_i])
                else:
                    logger.warning(
                        f"Analyze events did not process any events from month {year_month_i}"
                    )

    async def _compute_metrics(self, stats, events):
        # Step 2: Update all tables in a single transaction
        async with (self.metrics_pool.acquire() as conn):
            async with conn.transaction():
                # Update base tables first
                await self._update_base_tables(conn, stats)

                # Update rollup tables
                await self._update_dvm_stats_rollup(conn, stats)
                await self._update_kind_stats_rollup(conn, stats)

            # this does not need to be an atomic transaction, it's only adding new data
            await self._save_events(conn, events)

    def _check_date_passed_monthly_cleanup_threshold(
        self, current_year, current_month, event_year, event_month, event_day
    ):
        if current_year == event_year:
            if current_month < 12 and event_month > current_month:
                if event_day > self.monthly_cleanup_buffer_days:
                    logger.warning(
                        f"Event has month={event_month} and day={event_day}, which is past the buffer"
                        f" of {self.monthly_cleanup_buffer_days} of the current_month={current_month}"
                    )
                    return True

        elif current_year == event_year - 1:  # this is a new year scenario
            if event_day > self.monthly_cleanup_buffer_days:
                logger.warning(
                    f"Event has year={event_year}, month={event_month} and day={event_day}, which is"
                    f" past the buffer of {self.monthly_cleanup_buffer_days} of the"
                    f" current_month={current_month}"
                )
                return True

        elif current_year > event_year + 1:
            logger.error(
                f"Event is too far into the future with year={event_year}, month={event_month}, day={event_day}"
            )
            raise Exception(
                f"If this is being raised, there is a flaw earlier in the pipeline, this event "
                f"should have been ignored"
            )

        return False

    async def _analyze_events(self, events: List[dict]) -> BatchStats:
        """Analyze events and collect all necessary stats in memory."""
        stats = BatchStats(
            period_start=datetime.max.replace(tzinfo=timezone.utc),
            period_end=datetime.min.replace(tzinfo=timezone.utc),
        )

        current_state = await self._get_redis_state()

        while current_state is None:
            # if we can get the lock, we will set the state
            with BatchProcessorRedisLock(
                self.redis, self.redis_monthly_cleanup_lock_key, expire_seconds=15
            ) as one_time_attempt_lock:
                # double check current state is None
                current_state = await self._get_redis_state()
                if current_state:
                    break

                initial_state = {
                    "year": datetime.fromtimestamp(
                        events[0]["created_at"], tz=timezone.utc
                    ).year,
                    "month": datetime.fromtimestamp(
                        events[0]["created_at"], tz=timezone.utc
                    ).month,
                    "last_monthly_cleanup_completed": None,
                    "cleanup": {
                        "in_progress": False,
                        "requested": False,
                        "requested_by": None,
                        "started_at": None,
                    },
                }

                success = await self._set_redis_state(initial_state)
                if not success:
                    logger.error(f"Failed to set initial state in redis")

            await asyncio.sleep(2)
            current_state = await self._get_redis_state()

        # very important, this batch processor only processes batches where all events are in the same month
        first_event_month_seen = datetime.fromtimestamp(
            events[0]["created_at"], tz=timezone.utc
        ).month

        first_event_year_seen = datetime.fromtimestamp(
            events[0]["created_at"], tz=timezone.utc
        ).year

        logger.debug(
            f"Analyzing {len(events)} events with first event is {first_event_year_seen}/{first_event_month_seen} and"
            f"redis is {current_state['year']}/{current_state['month']}"
        )

        filtered_events = []
        warned_this_month_is_in_future = False  # simple flag to reduce log spam
        requested_monthly_cleanup = False
        for event in events:
            try:
                # Ensure we always have a timezone-aware datetime
                created_at = event["created_at"]
                if isinstance(created_at, str):
                    # If it's a string, parse it
                    timestamp = datetime.fromisoformat(created_at).replace(
                        tzinfo=timezone.utc
                    )
                elif isinstance(created_at, (int, float)):
                    # If it's a unix timestamp
                    timestamp = datetime.fromtimestamp(created_at, tz=timezone.utc)
                else:
                    # If it's already a datetime, ensure it has timezone
                    timestamp = (
                        created_at.replace(tzinfo=timezone.utc)
                        if created_at.tzinfo is None
                        else created_at
                    )

                event_year = timestamp.year
                event_month = timestamp.month
                event_day = timestamp.day

                # filter old events
                if event_year < current_state["year"]:
                    logger.warning(
                        f"Ignoring event with year={event_year}, month={event_month}, event_day={event_day}"
                        f" while current_year is {current_state['year']}"
                    )
                    filtered_events.append(event)
                    continue
                elif event_year > current_state["year"] + 1:
                    logger.error(f"Event timestamp is way too far into the future")
                    filtered_events.append(event)
                    continue
                elif (
                    event_year == current_state["year"]
                    and event_month < current_state["month"]
                ):
                    logger.warning(
                        f"Ignoring event with same year but {current_state['month']-event_month} months old"
                    )
                    filtered_events.append(event)
                    continue

                # if we have multiple months in this batch, trigger special logic (see process_events())
                if first_event_month_seen != event_month:
                    logger.warning(
                        f"We are in a multiple month batch scenario, running special logic to deal"
                        f" with multiple months"
                    )
                    raise MultipleMonthBatch()

                # Now we know the current batch contains events only in the current month or a future month, but
                # only in a single month. A future month should be rare, so if it happens, lets log as a warning
                if (
                    not warned_this_month_is_in_future
                    and event_month > current_state["month"]
                ):
                    logger.warning(
                        f"Event is in the future month {event_month}, currently"
                        f" processed by batch processor {self.unique_id}"
                    )
                    warned_this_month_is_in_future = True

                # check if monthly cleanup threshold has been passed
                # TODO - is there a race condition here? I think the 3 day buffer and 15s grace period prevent it...
                if not (
                    current_state["cleanup"]["requested"]
                    or current_state["cleanup"]["in_progress"]
                ):
                    if (
                        not requested_monthly_cleanup
                        and self._check_date_passed_monthly_cleanup_threshold(
                            current_state["year"],
                            current_state["month"],
                            event_year,
                            event_month,
                            event_day,
                        )
                    ):
                        requested_monthly_cleanup = await self._request_monthly_backup()

                stats.period_start = min(stats.period_start, timestamp)
                stats.period_end = max(stats.period_end, timestamp)

                kind = event["kind"]
                pubkey = event["pubkey"]
                event_id = event.get("id")

                if 5000 <= kind <= 5999:  # Request event
                    stats.period_requests += 1
                    stats.kind_requests[kind] += 1
                    stats.user_timestamps[pubkey] = max(
                        stats.user_timestamps[pubkey], timestamp
                    )
                    # Track each observation
                    stats.entity_activity["user"].append((pubkey, timestamp, event_id))
                    stats.entity_activity["kind"].append(
                        (str(kind), timestamp, event_id)
                    )

                elif 6000 <= kind <= 6999:  # Response event
                    request_kind = kind - 1000
                    stats.period_responses += 1
                    stats.kind_responses[request_kind] += 1
                    stats.user_is_dvm[pubkey] = True
                    stats.dvm_responses[pubkey] += 1
                    stats.dvm_timestamps[pubkey] = max(
                        stats.dvm_timestamps[pubkey], timestamp
                    )
                    stats.dvm_kinds[pubkey].add(request_kind)

                    stats.entity_activity["dvm"].append((pubkey, timestamp, event_id))
                    stats.entity_activity["kind"].append(
                        (str(kind), timestamp, event_id)
                    )

                elif kind == 7000:  # Feedback event
                    stats.period_feedback += 1
                    stats.dvm_feedback[pubkey] += 1
                    stats.dvm_timestamps[pubkey] = max(
                        stats.dvm_timestamps[pubkey], timestamp
                    )
                    stats.user_is_dvm[pubkey] = True
                    # Track each observation
                    stats.entity_activity["dvm"].append((pubkey, timestamp, event_id))

                stats.events_processed.append(event)
            except MultipleMonthBatch as e:
                # we need this to surface up to process_events() to trigger special logic there and re-do analyzing
                raise e
            except Exception as e:
                logger.error(f"Error processing event: {event}")
                logger.error(f"Error details: {str(e)}")
                logger.error(f"{traceback.format_exc()}")
                continue

        if len(filtered_events) > 0:
            logger.info(
                f"Dropped {len(filtered_events)} old events out of {len(events)} total events"
            )

        return stats

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
        Uses BLPOP with timeout for the first event, then gets more if available.
        """
        events = []
        start_time = time.time()

        try:
            # Track timing for debugging
            wait_start = time.time()

            # Wait for first event with timeout
            result = self.redis.blpop(self.queue_name, timeout=self.max_wait_seconds)

            wait_duration = time.time() - wait_start
            logger.debug(f"BLPOP wait duration: {wait_duration:.2f}s")

            if result:
                _, message = result
                event = self.extract_nostr_event(message)
                if event:
                    events.append(event)

                # Quick grab any additional events up to batch_size
                batch_start = time.time()
                while len(events) < self.batch_size:
                    if time.time() - start_time >= self.max_wait_seconds:
                        break

                    result = self.redis.lpop(self.queue_name)
                    if not result:
                        break

                    event = self.extract_nostr_event(result)
                    if event:
                        events.append(event)

                batch_duration = time.time() - batch_start
                logger.debug(
                    f"Batch collection duration: {batch_duration:.2f}s, events: {len(events)}"
                )

        except redis.RedisError as e:
            logger.error(f"Redis error getting batch: {e}")
            await asyncio.sleep(1)  # Back off on Redis errors
        except Exception as e:
            logger.error(f"Error getting batch of events: {e}")
            logger.error(traceback.format_exc())

        return events

    async def _update_base_tables(
        self, conn: asyncpg.Connection, stats: BatchStats
    ) -> None:
        """Update all base tables including entity activity tracking."""
        # 1. Update DVMs table
        if stats.dvm_timestamps:
            values = [
                (dvm_id, timestamp)
                for dvm_id, timestamp in stats.dvm_timestamps.items()
            ]
            await conn.executemany(
                """
                INSERT INTO dvms (id, first_seen, last_seen)
                VALUES ($1, $2, $2)
                ON CONFLICT (id) DO UPDATE 
                SET last_seen = GREATEST(dvms.last_seen, $2),
                    updated_at = CURRENT_TIMESTAMP
                """,
                values,
            )

        # 2. Update Users table
        if stats.user_timestamps:
            values = [
                (
                    user_id,
                    # If it's a DVM and we have an earlier timestamp, use that as first_seen
                    min(timestamp, stats.dvm_timestamps.get(user_id))
                    if stats.user_is_dvm[user_id] and user_id in stats.dvm_timestamps
                    else timestamp,
                    timestamp,
                    stats.user_is_dvm[user_id],
                    # For DVM discovery time, use the same early timestamp if available
                    stats.dvm_timestamps.get(user_id)
                    if stats.user_is_dvm[user_id]
                    else None,
                )
                for user_id, timestamp in stats.user_timestamps.items()
            ]
            await conn.executemany(
                """
                INSERT INTO users (id, first_seen, last_seen, is_dvm, discovered_as_dvm_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE 
                SET first_seen = LEAST(users.first_seen, $2), 
                    last_seen = GREATEST(users.last_seen, $3),
                    is_dvm = COALESCE(users.is_dvm, $4),
                    discovered_as_dvm_at = COALESCE(users.discovered_as_dvm_at, $5),
                    updated_at = CURRENT_TIMESTAMP
                """,
                values,
            )

        # 3. Update Kind-DVM Support table
        if stats.dvm_kinds:
            values = [
                (kind, dvm_id, stats.dvm_timestamps[dvm_id])
                for dvm_id, kinds in stats.dvm_kinds.items()
                for kind in kinds
            ]
            await conn.executemany(
                """
                INSERT INTO kind_dvm_support (kind, dvm, first_seen, last_seen, interaction_type)
                VALUES ($1, $2, $3, $3, 'both')
                ON CONFLICT (kind, dvm) DO UPDATE 
                SET last_seen = GREATEST(kind_dvm_support.last_seen, $3),
                    updated_at = CURRENT_TIMESTAMP
                """,
                values,
            )

        # 4. Update entity_activity table
        all_activity = []
        for entity_type, observations in stats.entity_activity.items():
            all_activity.extend(
                (entity_id, entity_type, timestamp, event_id)
                for entity_id, timestamp, event_id in observations
            )

        if all_activity:
            await conn.executemany(
                """
                INSERT INTO entity_activity (entity_id, entity_type, observed_at, event_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (entity_id, observed_at, event_id) DO NOTHING
                """,
                all_activity,
            )

    async def _update_dvms(self, conn: asyncpg.Connection, stats: BatchStats) -> None:
        """Update DVMs table with new DVMs and timestamps."""
        if not stats.dvm_timestamps:
            return

        # Build values for bulk insert/update
        values = [
            (dvm_id, timestamp) for dvm_id, timestamp in stats.dvm_timestamps.items()
        ]

        await conn.executemany(
            """
            INSERT INTO dvms (id, first_seen, last_seen)
            VALUES ($1, $2, $2)
            ON CONFLICT (id) DO UPDATE 
            SET last_seen = GREATEST(dvms.last_seen, $2),
                updated_at = CURRENT_TIMESTAMP
        """,
            values,
        )

    async def _update_users(self, conn: asyncpg.Connection, stats: BatchStats) -> None:
        """Update users table with new users and timestamps."""
        if not stats.user_timestamps:
            return

        # Build values for bulk insert/update
        values = [
            (
                user_id,
                timestamp,
                stats.user_is_dvm[user_id],
                timestamp if stats.user_is_dvm[user_id] else None,
            )
            for user_id, timestamp in stats.user_timestamps.items()
        ]

        await conn.executemany(
            """
            INSERT INTO users (id, first_seen, last_seen, is_dvm, discovered_as_dvm_at)
            VALUES ($1, $2, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE 
            SET last_seen = GREATEST(users.last_seen, $2),
                is_dvm = COALESCE(users.is_dvm, $3),
                discovered_as_dvm_at = COALESCE(users.discovered_as_dvm_at, $4),
                updated_at = CURRENT_TIMESTAMP
        """,
            values,
        )

    async def _update_kind_dvm_support(
        self, conn: asyncpg.Connection, stats: BatchStats
    ) -> None:
        """Update kind_dvm_support table."""
        if not stats.dvm_kinds:
            return

        values = [
            (kind, dvm_id, stats.dvm_timestamps[dvm_id])
            for dvm_id, kinds in stats.dvm_kinds.items()
            for kind in kinds
        ]

        await conn.executemany(
            """
            INSERT INTO kind_dvm_support (kind, dvm, first_seen, last_seen, interaction_type)
            VALUES ($1, $2, $3, $3, 'both')
            ON CONFLICT (kind, dvm) DO UPDATE 
            SET last_seen = GREATEST(kind_dvm_support.last_seen, $3),
                updated_at = CURRENT_TIMESTAMP
        """,
            values,
        )

    async def _update_dvm_stats_rollup(
        self, conn: asyncpg.Connection, stats: BatchStats
    ) -> None:
        """Update dvm_stats_rollups table with new stats."""
        if not stats.dvm_responses and not stats.dvm_feedback:
            return

        try:
            # Get previous running totals for each DVM
            dvm_ids = list(
                set(stats.dvm_responses.keys()) | set(stats.dvm_feedback.keys())
            )
            prev_totals = await conn.fetch(
                """
                SELECT dvm_id, 
                       COALESCE(MAX(running_total_responses), 0) as total_responses,
                       COALESCE(MAX(running_total_feedback), 0) as total_feedback
                FROM dvm_stats_rollups
                WHERE dvm_id = ANY($1)
                GROUP BY dvm_id
            """,
                dvm_ids,
            )

            prev_totals_dict = {
                row["dvm_id"]: (row["total_responses"], row["total_feedback"])
                for row in prev_totals
            }

            # Prepare values for new rollup entries
            values = [
                (
                    dvm_id,
                    stats.period_end,  # timestamp
                    stats.period_start,
                    stats.period_end,  # add period_end
                    stats.dvm_feedback.get(dvm_id, 0),
                    stats.dvm_responses.get(dvm_id, 0),
                    prev_totals_dict.get(dvm_id, (0, 0))[1]
                    + stats.dvm_feedback.get(dvm_id, 0),
                    prev_totals_dict.get(dvm_id, (0, 0))[0]
                    + stats.dvm_responses.get(dvm_id, 0),
                )
                for dvm_id in dvm_ids
            ]

            await conn.executemany(
                """
                INSERT INTO dvm_stats_rollups 
                    (dvm_id, timestamp, period_start, period_end, period_feedback, period_responses,
                     running_total_feedback, running_total_responses)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (dvm_id, timestamp) DO UPDATE
                SET period_start = EXCLUDED.period_start,
                    period_end = EXCLUDED.period_end,
                    period_feedback = EXCLUDED.period_feedback,
                    period_responses = EXCLUDED.period_responses,
                    running_total_feedback = EXCLUDED.running_total_feedback,
                    running_total_responses = EXCLUDED.running_total_responses
                """,
                values,
            )

            # Count how many were actually inserted vs updated using a separate query
            inserted_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM dvm_stats_rollups
                WHERE (dvm_id, timestamp) IN (
                    SELECT unnest($1::text[]), unnest($2::timestamptz[])
                )
                """,
                [v[0] for v in values],  # dvm_ids
                [v[1] for v in values],  # timestamps
            )

            if inserted_count < len(values):
                skipped = len(values) - inserted_count
                logger.warning(
                    f"Some DVM stats rollup records were updated rather than inserted ({skipped} updates)"
                )

        except Exception as e:
            logger.error(f"Error updating DVM stats rollups: {e}")
            logger.error(traceback.format_exc())
            raise

    async def _update_kind_stats_rollup(
        self, conn: asyncpg.Connection, stats: BatchStats
    ) -> None:
        """Update kind_stats_rollups table with new stats."""
        if not stats.kind_requests and not stats.kind_responses:
            return

        try:
            # Get previous running totals for each kind
            kinds = list(
                set(stats.kind_requests.keys()) | set(stats.kind_responses.keys())
            )
            prev_totals = await conn.fetch(
                """
                SELECT kind,
                       COALESCE(MAX(running_total_requests), 0) as total_requests,
                       COALESCE(MAX(running_total_responses), 0) as total_responses
                FROM kind_stats_rollups
                WHERE kind = ANY($1)
                GROUP BY kind
            """,
                kinds,
            )

            prev_totals_dict = {
                row["kind"]: (row["total_requests"], row["total_responses"])
                for row in prev_totals
            }

            values = [
                (
                    kind,
                    stats.period_end,  # timestamp
                    stats.period_start,
                    stats.period_end,  # add period_end
                    stats.kind_requests.get(kind, 0),
                    stats.kind_responses.get(kind, 0),
                    prev_totals_dict.get(kind, (0, 0))[0]
                    + stats.kind_requests.get(kind, 0),
                    prev_totals_dict.get(kind, (0, 0))[1]
                    + stats.kind_responses.get(kind, 0),
                )
                for kind in kinds
            ]

            await conn.executemany(
                """
                INSERT INTO kind_stats_rollups 
                    (kind, timestamp, period_start, period_end, period_requests, period_responses,
                     running_total_requests, running_total_responses)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (kind, timestamp) DO UPDATE
                SET period_start = EXCLUDED.period_start,
                    period_end = EXCLUDED.period_end,
                    period_requests = EXCLUDED.period_requests,
                    period_responses = EXCLUDED.period_responses,
                    running_total_requests = EXCLUDED.running_total_requests,
                    running_total_responses = EXCLUDED.running_total_responses
                """,
                values,
            )

            # Count how many were actually inserted vs updated using a separate query
            inserted_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM kind_stats_rollups
                WHERE (kind, timestamp) IN (
                    SELECT unnest($1::integer[]), unnest($2::timestamptz[])
                )
                """,
                [v[0] for v in values],  # kinds
                [v[1] for v in values],  # timestamps
            )

            if inserted_count < len(values):
                skipped = len(values) - inserted_count
                logger.warning(
                    f"Some kind stats rollup records were updated rather than inserted ({skipped} updates)"
                )

        except Exception as e:
            logger.error(f"Error updating kind stats rollups: {e}")
            logger.error(traceback.format_exc())
            raise

    async def get_metrics(
        self, conn: asyncpg.Connection, interval: str = "24 hours"
    ) -> dict:
        """
        Get metrics for a specified time interval using entity_activity table for unique counts.
        """
        # Validate interval
        valid_intervals = {"1 hour", "24 hours", "7 days", "30 days"}
        if interval not in valid_intervals:
            raise ValueError(f"Interval must be one of {valid_intervals}")

        metrics = (
            await conn.fetchrow(
                """
            WITH TimeWindowStats AS (
                SELECT
                    COALESCE(SUM(ksr.period_requests), 0)::integer as total_requests,
                    COALESCE(SUM(ksr.period_responses), 0)::integer as total_responses
                FROM kind_stats_rollups ksr
                WHERE CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE ksr.timestamp >= NOW() - ($1::interval)
                END
            ),
            PopularDVM AS (
                SELECT 
                    dvm_id, 
                    SUM(period_responses)::integer as total_responses
                FROM dvm_stats_rollups dsr
                WHERE CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE dsr.timestamp >= NOW() - ($1::interval)
                END
                GROUP BY dvm_id
                ORDER BY total_responses DESC
                LIMIT 1
            ),
            PopularKind AS (
                SELECT 
                    kind, 
                    SUM(period_requests)::integer as total_requests
                FROM kind_stats_rollups ksr2
                WHERE CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE ksr2.timestamp >= NOW() - ($1::interval)
                END
                GROUP BY kind
                ORDER BY total_requests DESC
                LIMIT 1
            ),
            CompetitiveKind AS (
                SELECT 
                    kind, 
                    COUNT(DISTINCT dvm)::integer as dvm_count
                FROM kind_dvm_support kds
                WHERE CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE kds.last_seen >= NOW() - ($1::interval)
                END
                GROUP BY kind
                ORDER BY dvm_count DESC
                LIMIT 1
            ),
            -- Use entity_activity for unique counts
            ActiveDVMs AS (
                SELECT COUNT(DISTINCT entity_id)::integer as total_dvms
                FROM entity_activity
                WHERE entity_type = 'dvm'
                AND CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE observed_at >= NOW() - ($1::interval)
                END
            ),
            ActiveKinds AS (
                SELECT COUNT(DISTINCT entity_id)::integer as total_kinds
                FROM entity_activity
                WHERE entity_type = 'kind'
                AND CAST(entity_id AS integer) BETWEEN 5000 AND 5999
                AND CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE observed_at >= NOW() - ($1::interval)
                END
            ),
            ActiveUsers AS (
                SELECT COUNT(DISTINCT entity_id)::integer as total_users
                FROM entity_activity
                WHERE entity_type = 'user'
                AND CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE observed_at >= NOW() - ($1::interval)
                END
            )
            SELECT 
                tws.total_requests,
                tws.total_responses,
                p1.dvm_id as popular_dvm,
                p2.kind as popular_kind,
                c.kind as competitive_kind,
                d.total_dvms,
                k.total_kinds,
                u.total_users
            FROM TimeWindowStats tws
            CROSS JOIN ActiveDVMs d
            CROSS JOIN ActiveKinds k
            CROSS JOIN ActiveUsers u
            LEFT JOIN PopularDVM p1 ON TRUE
            LEFT JOIN PopularKind p2 ON TRUE
            LEFT JOIN CompetitiveKind c ON TRUE
            """,
                interval,
            )
            or {
                "total_requests": 0,
                "total_responses": 0,
                "popular_dvm": None,
                "popular_kind": None,
                "competitive_kind": None,
                "total_dvms": 0,
                "total_kinds": 0,
                "total_users": 0,
            }
        )

        return metrics

    async def _update_window_stats(
        self, conn: asyncpg.Connection, stats: BatchStats
    ) -> None:
        """
        Update all time window stats in a single efficient operation.
        """

        window_sizes = ["1 hour", "24 hours", "7 days", "30 days"]

        # Map to convert window size strings to timedelta
        window_to_delta = {
            "1 hour": timedelta(hours=1),
            "24 hours": timedelta(days=1),
            "7 days": timedelta(days=7),
            "30 days": timedelta(days=30),
        }

        # Get metrics for each window size sequentially instead of using gather
        window_metrics = []
        for window_size in window_sizes:
            metrics = await self.get_metrics(conn, interval=window_size)
            window_metrics.append(metrics)

        # Prepare bulk insert for all windows
        values = []
        for window_size, metrics in zip(window_sizes, window_metrics):
            period_start = stats.period_end - window_to_delta[window_size]

            values.append(
                (
                    datetime.now(timezone.utc),
                    window_size,
                    period_start,
                    stats.period_end,
                    metrics["total_requests"],
                    metrics["total_responses"],
                    metrics["total_dvms"],
                    metrics["total_kinds"],
                    metrics["total_users"],
                    metrics["popular_dvm"],
                    metrics["popular_kind"],
                    metrics["competitive_kind"],
                )
            )

        # Bulk insert all windows at once
        await conn.executemany(
            """
            INSERT INTO time_window_stats (
                timestamp, window_size, period_start, period_end,
                total_requests, total_responses,
                unique_dvms, unique_kinds, unique_users,
                popular_dvm, popular_kind, competitive_kind
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            values,
        )

    async def _save_events(self, conn: asyncpg.Connection, events: List[dict]) -> None:
        """Save raw events to the events database."""
        if not events:
            return

        try:
            values = []
            for event in events:
                try:
                    # Just pass through the timestamp directly
                    created_at = int(event["created_at"])

                    values.append(
                        (
                            event.get("id"),
                            event.get("pubkey"),
                            created_at,  # Store as timestamp integer
                            event.get("kind"),
                            event.get("content", ""),
                            event.get("sig", ""),
                            json.dumps(event.get("tags", [])),
                            json.dumps(event),
                        )
                    )
                except Exception as e:
                    logger.error(f"Error processing event: {event.get('id', 'no-id')}")
                    logger.error(f"Created_at value: {event.get('created_at')}")
                    logger.error(f"Error details: {str(e)}")
                    continue

            if values:
                # Bulk insert events
                await conn.executemany(
                    """
                    INSERT INTO raw_events 
                        (id, pubkey, created_at, kind, content, sig, tags, raw_data)
                    VALUES ($1, $2, to_timestamp($3), $4, $5, $6, $7::jsonb, $8::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    values,
                )

        except Exception as e:
            logger.error(f"Error saving events to backup database: {e}")
            logger.error(traceback.format_exc())

    @staticmethod
    def format_metrics_row(timestamp, stats: BatchStats, queue_length: int) -> str:
        """Format batch stats as a table row."""
        return (
            f"{timestamp} | "
            f"Queue: {queue_length:>5} | "
            f"Δjobs: {stats.period_requests:>4}/{stats.period_responses:<4} | "
            f"Δusers: {len(stats.user_timestamps):>4} | "
            f"ΔDVMs: {len(stats.dvm_timestamps):>3} | "
            f"Δkinds: {len(stats.kind_requests):>3}"
        )

    async def process_forever(self):
        header = (
            "Timestamp            | Queue  | Δjobs req/res | Δusers | ΔDVMs | Δkinds"
        )
        logger.info("\n" + "=" * len(header))
        logger.info(header)
        logger.info("=" * len(header))

        consecutive_errors = 0
        events_processed = 0
        last_health_check = time.time()

        while True:
            try:
                # Get queue length before processing batch
                queue_length = self.redis.llen(self.queue_name)

                # Process batch of events
                process_start = time.time()
                events = await self.get_batch_of_events()

                if events:
                    await self.process_events(events)
                    events_processed += len(events)
                    consecutive_errors = 0  # Reset error count on success

                process_duration = time.time() - process_start
                logger.debug(
                    f"Batch processing complete - Events: {len(events)}, "
                    f"Duration: {process_duration:.2f}s"
                )

                # Health logging every minute
                if time.time() - last_health_check >= 60:
                    logger.info(
                        f"Health check - Processed {events_processed} events in last minute, "
                        f"Queue length: {queue_length}, Error count: {consecutive_errors}"
                    )
                    events_processed = 0  # Reset counter
                    last_health_check = time.time()

            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                logger.error(traceback.format_exc())
                consecutive_errors += 1

                if consecutive_errors >= 10:
                    logger.critical(
                        "Too many consecutive errors (10+), shutting down for safety..."
                    )
                    return  # Exit the process_forever loop

                # Exponential backoff on errors
                await asyncio.sleep(min(30, 2**consecutive_errors))

            # Short sleep to prevent tight loop if queue is empty
            if not events:
                await asyncio.sleep(0.1)


async def main():
    """Initialize and run the batch processor."""
    logger.info("Starting batch processor...")

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

        processor = BatchProcessor(
            redis_url=redis_url,
            metrics_pool=metrics_pool,
            batch_size=int(os.getenv("BATCH_SIZE", "100")),
            max_wait_seconds=int(os.getenv("MAX_WAIT_SECONDS", "5")),
            backtest_mode=os.getenv("BACKTEST_MODE", "false").lower() == "true",
        )

        await processor.process_forever()

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
