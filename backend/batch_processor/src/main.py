import os
import sys
import time
import asyncio
from datetime import datetime, timezone
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

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

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
    dvm_timestamps: Dict[str, datetime] = None  # dvm -> latest timestamp
    dvm_kinds: Dict[str, Set[int]] = None  # dvm -> set of kinds supported

    # Track users and their activities
    user_timestamps: Dict[str, datetime] = None  # user -> latest timestamp
    user_is_dvm: Dict[str, bool] = None  # user -> is_dvm flag

    # Track per-kind stats
    kind_requests: Dict[int, int] = None  # kind -> count of requests
    kind_responses: Dict[int, int] = None  # kind -> count of responses

    def __post_init__(self):
        self.dvm_responses = defaultdict(int)
        self.dvm_feedback = defaultdict(int)
        self.dvm_timestamps = defaultdict(
            lambda: datetime.min.replace(tzinfo=timezone.utc)
        )
        self.dvm_kinds = defaultdict(set)
        self.user_timestamps = defaultdict(
            lambda: datetime.min.replace(tzinfo=timezone.utc)
        )
        self.user_is_dvm = defaultdict(bool)
        self.kind_requests = defaultdict(int)
        self.kind_responses = defaultdict(int)


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

    async def process_events(self, events: List[dict]) -> None:
        """Process a batch of events and update all necessary tables atomically."""
        if not events:
            return

        # Step 1: Analyze all events in memory first
        stats = self._analyze_events(events)

        # Step 2: Update all tables in a single transaction
        async with self.metrics_pool.acquire() as conn:
            async with conn.transaction():
                # Update base tables first
                await self._update_dvms(conn, stats)
                await self._update_users(conn, stats)
                await self._update_kind_dvm_support(conn, stats)

                # Update rollup tables
                await self._update_dvm_stats_rollup(conn, stats)
                await self._update_kind_stats_rollup(conn, stats)
                await self._update_global_stats_rollup(conn, stats)

        # Step 3: Save all events to events db for backup and future reference
        async with self.events_pool.acquire() as conn:
            await self._save_events(conn, events)

    def _analyze_events(self, events: List[dict]) -> BatchStats:
        """Analyze events and collect all necessary stats in memory."""
        stats = BatchStats(
            period_start=datetime.max.replace(tzinfo=timezone.utc),
            period_end=datetime.min.replace(tzinfo=timezone.utc),
        )

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

                stats.period_start = min(stats.period_start, timestamp)
                stats.period_end = max(stats.period_end, timestamp)

                kind = event["kind"]
                pubkey = event["pubkey"]

                if 5000 <= kind <= 5999:  # Request event
                    stats.period_requests += 1
                    stats.kind_requests[kind] += 1
                    stats.user_timestamps[pubkey] = max(
                        stats.user_timestamps[pubkey], timestamp
                    )

                elif 6000 <= kind <= 6999:  # Response event
                    stats.period_responses += 1
                    request_kind = self._get_request_kind_from_response(event)
                    if request_kind and 5000 <= request_kind <= 5999:
                        stats.kind_responses[request_kind] += 1
                        stats.dvm_responses[pubkey] += 1
                        stats.dvm_timestamps[pubkey] = max(
                            stats.dvm_timestamps[pubkey], timestamp
                        )
                        stats.dvm_kinds[pubkey].add(request_kind)
                        stats.user_is_dvm[pubkey] = True

                elif kind == 7000:  # Feedback event
                    stats.period_feedback += 1
                    stats.dvm_feedback[pubkey] += 1
                    stats.dvm_timestamps[pubkey] = max(
                        stats.dvm_timestamps[pubkey], timestamp
                    )
                    stats.user_is_dvm[pubkey] = True

            except Exception as e:
                logger.error(f"Error processing event: {event}")
                logger.error(f"Error details: {str(e)}")
                continue

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
        Uses BRPOP with timeout for the first event, then gets more if available.
        """
        events = []
        start_time = time.time()

        try:
            # Track timing for debugging
            wait_start = time.time()

            # Wait for first event with timeout
            result = self.redis.brpop(self.queue_name, timeout=self.max_wait_seconds)

            wait_duration = time.time() - wait_start
            logger.debug(f"BRPOP wait duration: {wait_duration:.2f}s")

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
        Get metrics for a specified time interval with improved filtering and accuracy.
        """
        # Validate interval
        valid_intervals = {"1 hour", "24 hours", "7 days", "30 days", "all time"}
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
            ActiveDVMs AS (
                SELECT COUNT(DISTINCT id)::integer as total_dvms
                FROM dvms d
                WHERE CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE d.last_seen >= NOW() - ($1::interval)
                END
            ),
            ActiveKinds AS (
                SELECT COUNT(DISTINCT kind)::integer as total_kinds
                FROM kind_stats_rollups ksr3
                WHERE CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE ksr3.timestamp >= NOW() - ($1::interval)
                END
            ),
            ActiveUsers AS (
                SELECT COUNT(DISTINCT id)::integer as total_users
                FROM users u
                WHERE CASE 
                    WHEN $1 = 'all time' THEN TRUE
                    ELSE u.last_seen >= NOW() - ($1::interval)
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
        current_timestamp = datetime.now(timezone.utc)
        window_sizes = ["1 hour", "24 hours", "7 days", "30 days", "all time"]

        # Get all window metrics in one operation
        window_metrics = await asyncio.gather(
            *[
                self.get_metrics(conn, interval=window_size)
                for window_size in window_sizes
            ]
        )

        # Prepare bulk insert for all windows
        values = [
            (
                current_timestamp,
                window_size,
                metrics["total_requests"],
                metrics["total_responses"],
                metrics["total_dvms"],
                metrics["total_kinds"],
                metrics["total_users"],
                metrics["popular_dvm"],
                metrics["popular_kind"],
                metrics["competitive_kind"],
            )
            for window_size, metrics in zip(window_sizes, window_metrics)
        ]

        # Bulk insert/update all windows at once
        await conn.executemany(
            """
            INSERT INTO time_window_stats (
                timestamp, window_size, total_requests, total_responses,
                unique_dvms, unique_kinds, unique_users,
                popular_dvm, popular_kind, competitive_kind
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (timestamp, window_size) 
            DO UPDATE SET
                total_requests = EXCLUDED.total_requests,
                total_responses = EXCLUDED.total_responses,
                unique_dvms = EXCLUDED.unique_dvms,
                unique_kinds = EXCLUDED.unique_kinds,
                unique_users = EXCLUDED.unique_users,
                popular_dvm = EXCLUDED.popular_dvm,
                popular_kind = EXCLUDED.popular_kind,
                competitive_kind = EXCLUDED.competitive_kind,
                updated_at = CURRENT_TIMESTAMP
            """,
            values,
        )

    async def _update_global_stats_rollup(
        self, conn: asyncpg.Connection, stats: BatchStats
    ) -> None:
        """Update global_stats_rollups and time_window_stats tables with new stats."""
        try:
            # First do the existing global stats rollup update
            metrics = await self.get_metrics(conn, interval="24 hours")
            last_totals = (
                await conn.fetchrow(
                    """
                        SELECT 
                            COALESCE(MAX(running_total_requests), 0)::integer as last_requests,
                            COALESCE(MAX(running_total_responses), 0)::integer as last_responses
                        FROM global_stats_rollups
                        """
                )
                or {"last_requests": 0, "last_responses": 0}
            )

            new_total_requests = last_totals["last_requests"] + stats.period_requests
            new_total_responses = last_totals["last_responses"] + stats.period_responses
            current_timestamp = datetime.now(timezone.utc)

            async with conn.transaction():
                # Insert new global stats rollup
                await conn.execute(
                    """
                    INSERT INTO global_stats_rollups (
                        timestamp, period_start, period_end, period_requests, period_responses,
                        running_total_requests, running_total_responses,
                        running_total_unique_dvms, running_total_unique_kinds,
                        running_total_unique_users
                    )
                    VALUES ($1, $2, $3, $4::integer, $5::integer, $6::integer, $7::integer, 
                            $8::integer, $9::integer, $10::integer)
                    """,
                    current_timestamp,
                    stats.period_start,
                    stats.period_end,
                    int(stats.period_requests),
                    int(stats.period_responses),
                    new_total_requests,
                    new_total_responses,
                    metrics["total_dvms"],
                    metrics["total_kinds"],
                    metrics["total_users"],
                )

                # Update all time window stats efficiently
                await self._update_window_stats(conn, stats)

        except Exception as e:
            logger.error(f"Error updating stats rollups: {e}")
            logger.error(traceback.format_exc())
            raise

    def _get_request_kind_from_response(self, response_event: dict) -> int:
        """Extract the original request kind from a response event's tags."""
        try:
            for tag in response_event["tags"]:
                if tag[0] == "k":
                    return int(tag[1])
            # If no 'k' tag found, attempt to extract from 'e' tag reference
            for tag in response_event["tags"]:
                if tag[0] == "e":
                    # The kind should be response_kind - 1000 to get request kind
                    return response_event["kind"] - 1000
        except (KeyError, IndexError, ValueError):
            return None
        return None

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
            min_size=5,
            max_size=20,
        )

        # Initialize events database connection pool
        logger.info("Connecting to events database...")
        events_pool = await asyncpg.create_pool(
            user=os.getenv("EVENTS_POSTGRES_USER", "postgres"),
            password=os.getenv("EVENTS_POSTGRES_PASSWORD", "postgres"),
            database=os.getenv("EVENTS_POSTGRES_DB", "dvmdash_events"),
            host=os.getenv("EVENTS_POSTGRES_HOST", "localhost"),
            min_size=5,
            max_size=20,
        )

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        logger.info(f"Connecting to Redis at {redis_url}")

        processor = BatchProcessor(
            redis_url=redis_url,
            metrics_pool=metrics_pool,
            events_pool=events_pool,
            batch_size=int(os.getenv("BATCH_SIZE", "100")),
            max_wait_seconds=int(os.getenv("MAX_WAIT_SECONDS", "5")),
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
        if "events_pool" in locals():
            await events_pool.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
