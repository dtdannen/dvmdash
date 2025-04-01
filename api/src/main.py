# api/src/main.py


from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
import asyncpg
import redis
import time
import json
from typing import Optional, List, Union
from enum import Enum
from fastapi import Query
from loguru import logger

# Configure loguru based on LOG_LEVEL environment variable
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logger.remove()  # Remove default handler
logger.add(
    sink=lambda msg: print(msg),  # Use print as the sink to maintain console output
    level=log_level,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

logger.info(f"Logging configured with level: {log_level}")

from admin_routes import router as admin_router
from relay_config import RelayConfigManager


class DVMTimeSeriesData(BaseModel):
    time: str
    total_responses: int
    total_feedback: int


class DVMStatsResponse(BaseModel):
    dvm_id: str
    dvm_name: Optional[str] = None
    dvm_about: Optional[str] = None
    dvm_picture: Optional[str] = None
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    total_responses: int
    total_feedback: int
    supported_kinds: List[int] = []
    time_series: List[DVMTimeSeriesData]


class DVMListItem(BaseModel):
    id: str
    last_seen: datetime
    is_active: bool
    supported_kinds: List[int]
    num_supporting_kinds: int
    total_responses: Optional[int] = None
    total_feedback: Optional[int] = None
    total_events: Optional[int] = None
    dvm_name: Optional[str] = None
    dvm_about: Optional[str] = None
    dvm_picture: Optional[str] = None


class DVMListResponse(BaseModel):
    dvms: List[DVMListItem]


class TimeWindow(str, Enum):
    ONE_HOUR = "1h"
    ONE_DAY = "24h"
    ONE_WEEK = "7d"
    ONE_MONTH = "30d"

    def to_db_value(self) -> str:
        """Convert frontend time window to database value"""
        mapping = {
            "1h": "1 hour",
            "24h": "24 hours",
            "7d": "7 days",
            "30d": "30 days",
        }
        return mapping[self.value]


class TimeSeriesData(BaseModel):
    time: str
    total_requests: int
    total_responses: int
    unique_users: int
    unique_dvms: int


class GlobalStatsResponse(BaseModel):
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_responses: int
    unique_dvms: int
    unique_kinds: int
    unique_users: int
    popular_dvm: Optional[str]
    popular_kind: Optional[int]
    competitive_kind: Optional[int]
    time_series: List[TimeSeriesData]


class KindTimeSeriesData(BaseModel):
    time: str
    total_requests: int
    total_responses: int


class KindStatsResponse(BaseModel):
    kind: int
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_responses: int
    num_supporting_dvms: int
    supporting_dvms: List[str]
    time_series: List[KindTimeSeriesData]


class KindListItem(BaseModel):
    kind: int
    last_seen: datetime
    num_supporting_dvms: int
    total_requests: Optional[int] = None
    total_responses: Optional[int] = None


class KindListResponse(BaseModel):
    kinds: List[KindListItem]


app = FastAPI(title="DVMDash API")

# Include admin routes
app.include_router(admin_router)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "*")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint for App Platform"""
    try:
        # Test database connection
        async with app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def get_db_pool():
    return await asyncpg.create_pool(
        user=os.getenv("POSTGRES_USER", "devuser"),
        password=os.getenv("POSTGRES_PASSWORD", "devpass"),
        database=os.getenv("POSTGRES_DB", "dvmdash_pipeline"),
        host=os.getenv("POSTGRES_HOST", "postgres_pipeline"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
    )


def clean_stale_collectors(redis_client):
    """Remove stale collectors from Redis"""
    current_time = int(time.time())
    # Increase the threshold to 30 minutes to give collectors more time to start up
    active_threshold = current_time - (30 * 60)
    
    collectors = redis_client.smembers('dvmdash:collectors:active')
    removed_count = 0
    
    for collector_id in collectors:
        heartbeat = redis_client.get(f'dvmdash:collector:{collector_id}:heartbeat')
        # Only remove collectors that have a heartbeat older than the threshold
        # Don't remove collectors that haven't sent a heartbeat yet (they might be starting up)
        if heartbeat and int(heartbeat) < active_threshold:
            print(f"Removing stale collector: {collector_id}")
            # Remove from active set
            redis_client.srem('dvmdash:collectors:active', collector_id)
            # Clean up all collector keys
            for key in redis_client.keys(f'dvmdash:collector:{collector_id}:*'):
                redis_client.delete(key)
            removed_count += 1
    
    if removed_count > 0:
        print(f"Cleaned up {removed_count} stale collectors")
    return removed_count

@app.on_event("startup")
async def startup():
    app.state.pool = await get_db_pool()
    
    # Initialize Redis connection
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    app.state.redis = redis.from_url(redis_url)
    
    # Clean up stale collectors
    clean_stale_collectors(app.state.redis)
    
    # Initialize relays in Redis if none exist
    relays = RelayConfigManager.get_all_relays(app.state.redis)
    if not relays:
        print("No relays found in Redis. Initializing default relays...")
        default_relays_str = os.getenv("DEFAULT_RELAYS", "wss://relay.damus.io,wss://relay.primal.net")
        default_relays = [url.strip() for url in default_relays_str.split(",") if url.strip()]
        
        for relay_url in default_relays:
            # Add relay with normal activity level
            success = RelayConfigManager.add_relay(app.state.redis, relay_url, "normal")
            if success:
                print(f"Added relay: {relay_url}")
            else:
                print(f"Failed to add relay: {relay_url}")
        
        # Request relay distribution from coordinator
        RelayConfigManager.request_relay_distribution(app.state.redis)
        print("Requested relay distribution from coordinator")


@app.on_event("shutdown")
async def shutdown():
    await app.state.pool.close()


@app.get("/api/stats/global/latest", response_model=GlobalStatsResponse)
async def get_latest_global_stats(
    timeRange: TimeWindow = Query(
        default=TimeWindow.ONE_MONTH,
        alias="timeRange",
        description="Time window for stats",
    )
):
    async with app.state.pool.acquire() as conn:
        # Get the latest stats
        stats_query = """
            SELECT 
                timestamp,
                period_start,
                period_end,
                total_requests,
                total_responses,
                unique_users,
                unique_kinds,
                unique_dvms,
                popular_dvm,
                popular_kind,
                competitive_kind
            FROM time_window_stats 
            WHERE window_size = $1
            ORDER BY timestamp DESC 
            LIMIT 1
        """
        stats = await conn.fetchrow(stats_query, timeRange.to_db_value())

        if not stats:
            raise HTTPException(
                status_code=404,
                detail=f"No global stats found for window size {timeRange}",
            )

        # Get time series data
        timeseries_query = """
            WITH intervals AS (
                SELECT generate_series(
                    CASE 
                        WHEN $1 = '1 hour' THEN NOW() - INTERVAL '1 hour'
                        WHEN $1 = '24 hours' THEN NOW() - INTERVAL '24 hours'
                        WHEN $1 = '7 days' THEN NOW() - INTERVAL '7 days'
                        WHEN $1 = '30 days' THEN NOW() - INTERVAL '30 days'
                    END,
                    NOW(),
                    CASE 
                        WHEN $1 = '1 hour' THEN INTERVAL '5 minutes'
                        WHEN $1 = '24 hours' THEN INTERVAL '1 hour'
                        WHEN $1 = '7 days' THEN INTERVAL '6 hours'
                        WHEN $1 = '30 days' THEN INTERVAL '1 day'
                    END
                ) AS interval_start
            ),
            active_dvms AS (
                SELECT DISTINCT entity_id
                FROM entity_activity
                WHERE entity_type = 'dvm'
                AND observed_at >= CASE 
                    WHEN $1 = '1 hour' THEN NOW() - INTERVAL '1 hour'
                    WHEN $1 = '24 hours' THEN NOW() - INTERVAL '24 hours'
                    WHEN $1 = '7 days' THEN NOW() - INTERVAL '7 days'
                    WHEN $1 = '30 days' THEN NOW() - INTERVAL '30 days'
                END
            ),
            interval_stats AS (
                SELECT 
                    i.interval_start,
                    COUNT(DISTINCT CASE 
                        WHEN ea.kind BETWEEN 5000 AND 5999 
                        THEN ea.event_id 
                    END) as total_requests,
                    COUNT(DISTINCT CASE 
                        WHEN ea.kind BETWEEN 6000 AND 6999 
                        THEN ea.event_id 
                    END) as total_responses,
                    COUNT(DISTINCT CASE 
                        WHEN ea.entity_type = 'user' 
                        THEN ea.entity_id 
                    END) as unique_users,
                    COUNT(DISTINCT CASE 
                        WHEN ea.entity_type = 'dvm' AND ea.entity_id IN (SELECT entity_id FROM active_dvms)
                        THEN ea.entity_id 
                    END) as unique_dvms
                FROM intervals i
                LEFT JOIN entity_activity ea ON 
                    ea.observed_at >= i.interval_start 
                    AND ea.observed_at < i.interval_start + 
                        CASE 
                            WHEN $1 = '1 hour' THEN INTERVAL '5 minutes'
                            WHEN $1 = '24 hours' THEN INTERVAL '1 hour'
                            WHEN $1 = '7 days' THEN INTERVAL '6 hours'
                            WHEN $1 = '30 days' THEN INTERVAL '1 day'
                        END
                GROUP BY i.interval_start
                ORDER BY i.interval_start
            )
            SELECT
                to_char(interval_start, 'YYYY-MM-DD HH24:MI:SS') as time,
                total_requests,
                total_responses,
                unique_users,
                unique_dvms
            FROM interval_stats
        """

        timeseries_rows = await conn.fetch(timeseries_query, timeRange.to_db_value())
        time_series = [dict(row) for row in timeseries_rows]

        # Combine all data
        resulting_data = {**dict(stats), "time_series": time_series}

        return resulting_data


@app.get("/api/dvms", response_model=DVMListResponse)
async def list_dvms(
    limit: int = Query(
        default=100, ge=1, le=1000, description="Number of DVMs to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of DVMs to skip"),
    timeRange: TimeWindow = Query(
        default=TimeWindow.ONE_MONTH,
        alias="timeRange",
        description="Time window for stats and activity filtering",
    ),
):
    """
    Get a list of DVMs that have had activity within the specified time range.
    Returns DVMs ordered by last seen timestamp.
    """
    async with app.state.pool.acquire() as conn:
        query = """
            WITH active_dvms AS (
                SELECT DISTINCT entity_id as dvm_id
                FROM entity_activity
                WHERE entity_type = 'dvm'
                AND observed_at >= CASE 
                    WHEN $3 = '1 hour' THEN NOW() - INTERVAL '1 hour'
                    WHEN $3 = '24 hours' THEN NOW() - INTERVAL '24 hours'
                    WHEN $3 = '7 days' THEN NOW() - INTERVAL '7 days'
                    WHEN $3 = '30 days' THEN NOW() - INTERVAL '30 days'
                END
            ),
            dvm_kinds AS (
                SELECT 
                    dvm,
                    array_agg(kind ORDER BY kind) as supported_kinds
                FROM kind_dvm_support
                GROUP BY dvm
            ),
            latest_stats AS (
                SELECT DISTINCT ON (dvm_id)
                    dvm_id,
                    total_responses,
                    total_feedback
                FROM dvm_time_window_stats
                WHERE window_size = $3
                ORDER BY dvm_id, timestamp DESC
            )
            SELECT 
                d.id,
                d.last_seen,
                d.is_active,
                d.last_profile_event_raw_json,
                COALESCE(dk.supported_kinds, ARRAY[]::integer[]) as supported_kinds,
                (SELECT COUNT(*) FROM kind_dvm_support WHERE dvm = d.id) as num_supporting_kinds,
                s.total_responses,
                s.total_feedback,
                (COALESCE(s.total_responses, 0) + COALESCE(s.total_feedback, 0)) as total_events
            FROM dvms d
            JOIN active_dvms ad ON d.id = ad.dvm_id
            LEFT JOIN dvm_kinds dk ON dk.dvm = d.id
            LEFT JOIN latest_stats s ON s.dvm_id = d.id
            ORDER BY d.last_seen DESC
            LIMIT $1
            OFFSET $2
        """
        
        rows = await conn.fetch(query, limit, offset, timeRange.to_db_value())

        # Process rows to extract profile information
        processed_rows = []
        for row in rows:
            row_dict = dict(row)
            
            # Extract profile information
            profile_json = row_dict.pop('last_profile_event_raw_json', None)
            if profile_json:
                try:
                    if isinstance(profile_json, str):
                        profile_json = json.loads(profile_json)
                    
                    # Extract name
                    if "name" in profile_json:
                        row_dict["dvm_name"] = profile_json["name"]
                    
                    # Extract about
                    if "about" in profile_json:
                        row_dict["dvm_about"] = profile_json["about"]
                    
                    # Extract picture (check both picture and image fields)
                    if "picture" in profile_json:
                        row_dict["dvm_picture"] = profile_json["picture"]
                    elif "image" in profile_json:
                        row_dict["dvm_picture"] = profile_json["image"]
                except Exception as e:
                    print(f"Error parsing profile JSON for DVM {row_dict['id']}: {e}")
            
            processed_rows.append(row_dict)

        return {"dvms": processed_rows}


@app.get("/api/stats/dvm/{dvm_id}", response_model=DVMStatsResponse)
async def get_dvm_stats(
    dvm_id: str = Path(..., description="DVM ID"),
    timeRange: TimeWindow = Query(
        default=TimeWindow.ONE_MONTH,
        alias="timeRange",
        description="Time window for stats",
    ),
):
    logger.debug(f"Getting stats for DVM {dvm_id} with timeRange {timeRange}")

    async with app.state.pool.acquire() as conn:
        # First check if DVM exists
        dvm_check = await conn.fetchrow(
            "SELECT id, is_active, last_profile_event_raw_json FROM dvms WHERE id = $1", dvm_id
        )
        if not dvm_check:
            logger.debug(f"DVM {dvm_id} not found")
            raise HTTPException(status_code=404, detail=f"DVM {dvm_id} not found")
        if not dvm_check["is_active"]:
            logger.debug(f"DVM {dvm_id} is no longer active")
            raise HTTPException(
                status_code=404, detail=f"DVM {dvm_id} is no longer active"
            )

        logger.debug(f"Found active DVM {dvm_id}")
        
        # Extract profile information
        dvm_name = None
        dvm_about = None
        dvm_picture = None
        
        if dvm_check["last_profile_event_raw_json"]:
            try:
                profile_json = dvm_check["last_profile_event_raw_json"]
                if isinstance(profile_json, str):
                    profile_json = json.loads(profile_json)
                
                # Extract name
                if "name" in profile_json:
                    dvm_name = profile_json["name"]
                
                # Extract about
                if "about" in profile_json:
                    dvm_about = profile_json["about"]
                
                # Extract picture (check both picture and image fields)
                if "picture" in profile_json:
                    dvm_picture = profile_json["picture"]
                elif "image" in profile_json:
                    dvm_picture = profile_json["image"]
                
                logger.debug(f"Extracted profile data: name={dvm_name}, has_about={bool(dvm_about)}, has_picture={bool(dvm_picture)}")
            except Exception as e:
                logger.error(f"Error parsing profile JSON: {e}")

        # Get latest stats from dvm_time_window_stats
        stats_query = """
            SELECT 
                dvm_id,
                timestamp,
                period_start,
                period_end,
                total_responses,
                total_feedback
            FROM dvm_time_window_stats 
            WHERE dvm_id = $1
            AND window_size = $2
            ORDER BY timestamp DESC 
            LIMIT 1
        """
        
        logger.debug(f"Fetching stats with window size {timeRange.to_db_value()}")
        stats = await conn.fetchrow(stats_query, dvm_id, timeRange.to_db_value())

        if not stats:
            logger.debug(f"No stats found, returning empty stats")
            # Return empty stats if no data exists
            stats = {
                "dvm_id": dvm_id,
                "timestamp": datetime.now(),
                "period_start": datetime.now(),
                "period_end": datetime.now(),
                "total_responses": 0,
                "total_feedback": 0
            }

        logger.debug(f"Found stats: {stats}")

        # Calculate time series data from entity_activity
        logger.debug(f"Calculating time series data")
        timeseries_query = """
            WITH intervals AS (
                SELECT generate_series(
                    CASE 
                        WHEN $2 = '1 hour' THEN NOW() - INTERVAL '1 hour'
                        WHEN $2 = '24 hours' THEN NOW() - INTERVAL '24 hours'
                        WHEN $2 = '7 days' THEN NOW() - INTERVAL '7 days'
                        WHEN $2 = '30 days' THEN NOW() - INTERVAL '30 days'
                    END,
                    NOW(),
                    CASE 
                        WHEN $2 = '1 hour' THEN INTERVAL '5 minutes'
                        WHEN $2 = '24 hours' THEN INTERVAL '1 hour'
                        WHEN $2 = '7 days' THEN INTERVAL '6 hours'
                        WHEN $2 = '30 days' THEN INTERVAL '1 day'
                    END
                ) AS interval_start
            ),
            interval_stats AS (
                SELECT 
                    i.interval_start,
                    COUNT(DISTINCT CASE 
                        WHEN ea.kind >= 6000 AND ea.kind <= 6999 
                        THEN ea.event_id 
                    END) as responses,
                    COUNT(DISTINCT CASE 
                        WHEN ea.kind = 7000 
                        THEN ea.event_id 
                    END) as feedback
                FROM intervals i
                LEFT JOIN entity_activity ea ON 
                    ea.entity_type = 'dvm'
                    AND ea.entity_id = $1
                    AND ea.observed_at >= i.interval_start 
                    AND ea.observed_at < i.interval_start + 
                        CASE 
                            WHEN $2 = '1 hour' THEN INTERVAL '5 minutes'
                            WHEN $2 = '24 hours' THEN INTERVAL '1 hour'
                            WHEN $2 = '7 days' THEN INTERVAL '6 hours'
                            WHEN $2 = '30 days' THEN INTERVAL '1 day'
                        END
                GROUP BY i.interval_start
                ORDER BY i.interval_start
            )
            SELECT
                to_char(interval_start, 'YYYY-MM-DD HH24:MI:SS') as time,
                COALESCE(responses, 0) as total_responses,
                COALESCE(feedback, 0) as total_feedback
            FROM interval_stats
        """

        timeseries_rows = await conn.fetch(
            timeseries_query, dvm_id, timeRange.to_db_value()
        )
        time_series = [dict(row) for row in timeseries_rows]
        logger.debug(f"Found {len(time_series)} time series data points")

        # Get supported kinds for this DVM
        supported_kinds_query = """
            SELECT array_agg(kind ORDER BY kind) as supported_kinds
            FROM kind_dvm_support
            WHERE dvm = $1
            GROUP BY dvm
        """
        
        logger.debug(f"Fetching supported kinds")
        supported_kinds_row = await conn.fetchrow(supported_kinds_query, dvm_id)
        supported_kinds = supported_kinds_row["supported_kinds"] if supported_kinds_row else []
        logger.debug(f"Found {len(supported_kinds) if supported_kinds else 0} supported kinds")

        result = {
            **dict(stats), 
            "time_series": time_series,
            "dvm_name": dvm_name,
            "dvm_about": dvm_about,
            "dvm_picture": dvm_picture,
            "supported_kinds": supported_kinds or []
        }
        logger.debug(f"Returning result with {len(result['time_series'])} time series points")
        return result


@app.get("/api/stats/kind/{kind_id}", response_model=KindStatsResponse)
async def get_kind_stats(
    kind_id: int = Path(..., description="Kind ID"),
    timeRange: TimeWindow = Query(
        default=TimeWindow.ONE_MONTH,
        alias="timeRange",
        description="Time window for stats",
    ),
):
    async with app.state.pool.acquire() as conn:
        stats_query = """
            WITH stats AS (
                SELECT 
                    kind,
                    timestamp,
                    period_start,
                    period_end,
                    total_requests,
                    total_responses
                FROM kind_time_window_stats 
                WHERE kind = $1
                AND window_size = $2
                ORDER BY timestamp DESC 
                LIMIT 1
            ),
            supporting_dvms AS (
                SELECT array_agg(dvm) as dvms, COUNT(*) as dvm_count
                FROM kind_dvm_support
                WHERE kind = $1
                GROUP BY kind
            )
            SELECT 
                s.*,
                COALESCE(d.dvm_count, 0) as num_supporting_dvms,
                COALESCE(d.dvms, ARRAY[]::text[]) as supporting_dvms
            FROM stats s
            LEFT JOIN supporting_dvms d ON true
        """
        stats = await conn.fetchrow(stats_query, kind_id, timeRange.to_db_value())

        if not stats:
            # Check if kind exists
            kind_check = await conn.fetchrow(
                "SELECT kind FROM kind_dvm_support WHERE kind = $1 LIMIT 1", kind_id
            )
            if not kind_check:
                raise HTTPException(status_code=404, detail=f"Kind {kind_id} not found")
            # Return empty stats if kind exists but has no data
            return {
                "kind": kind_id,
                "timestamp": datetime.now(),
                "period_start": datetime.now(),
                "period_end": datetime.now(),
                "total_requests": 0,
                "total_responses": 0,
                "num_supporting_dvms": 0,
                "supporting_dvms": [],
                "time_series": [],
            }

        timeseries_query = """
            WITH intervals AS (
                SELECT generate_series(
                    CASE 
                        WHEN $2 = '1 hour' THEN NOW() - INTERVAL '1 hour'
                        WHEN $2 = '24 hours' THEN NOW() - INTERVAL '24 hours'
                        WHEN $2 = '7 days' THEN NOW() - INTERVAL '7 days'
                        WHEN $2 = '30 days' THEN NOW() - INTERVAL '30 days'
                    END,
                    NOW(),
                    CASE 
                        WHEN $2 = '1 hour' THEN INTERVAL '5 minutes'
                        WHEN $2 = '24 hours' THEN INTERVAL '1 hour'
                        WHEN $2 = '7 days' THEN INTERVAL '6 hours'
                        WHEN $2 = '30 days' THEN INTERVAL '1 day'
                    END
                ) AS interval_start
            ),
            interval_stats AS (
                SELECT 
                    i.interval_start,
                    COUNT(DISTINCT CASE WHEN ea.kind = $1 THEN ea.event_id END) as requests,
                    COUNT(DISTINCT CASE WHEN ea.kind = $1 + 1000 THEN ea.event_id END) as responses
                FROM intervals i
                LEFT JOIN entity_activity ea ON 
                    ea.observed_at >= i.interval_start AND 
                    ea.observed_at < i.interval_start + 
                        CASE 
                            WHEN $2 = '1 hour' THEN INTERVAL '5 minutes'
                            WHEN $2 = '24 hours' THEN INTERVAL '1 hour'
                            WHEN $2 = '7 days' THEN INTERVAL '6 hours'
                            WHEN $2 = '30 days' THEN INTERVAL '1 day'
                        END
                GROUP BY i.interval_start
                ORDER BY i.interval_start
            )
            SELECT
                to_char(interval_start, 'YYYY-MM-DD HH24:MI:SS') as time,
                COALESCE(requests, 0) as total_requests,
                COALESCE(responses, 0) as total_responses
            FROM interval_stats
        """

        timeseries_rows = await conn.fetch(
            timeseries_query, kind_id, timeRange.to_db_value()
        )
        time_series = [dict(row) for row in timeseries_rows]

        return {**dict(stats), "time_series": time_series}


@app.get("/api/kinds", response_model=KindListResponse)
async def list_kinds(
    limit: int = Query(
        default=100, ge=1, le=1000, description="Number of kinds to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of kinds to skip"),
    timeRange: TimeWindow = Query(
        default=TimeWindow.ONE_MONTH,
        alias="timeRange",
        description="Time window for stats and activity filtering",
    ),
):
    """
    Get a list of kinds that have had activity within the specified time range.
    Returns kinds ordered by last seen timestamp.
    """
    async with app.state.pool.acquire() as conn:
        query = """
            WITH active_kinds AS (
                SELECT DISTINCT kind
                FROM entity_activity
                WHERE observed_at >= CASE 
                    WHEN $3 = '1 hour' THEN NOW() - INTERVAL '1 hour'
                    WHEN $3 = '24 hours' THEN NOW() - INTERVAL '24 hours'
                    WHEN $3 = '7 days' THEN NOW() - INTERVAL '7 days'
                    WHEN $3 = '30 days' THEN NOW() - INTERVAL '30 days'
                END
                AND (
                    (kind BETWEEN 5000 AND 5999) OR  -- Request kinds
                    (kind BETWEEN 6000 AND 6999)     -- Response kinds
                )
            ),
            dvm_counts AS (
                SELECT 
                    kind,
                    COUNT(DISTINCT dvm) as num_supporting_dvms,
                    MAX(last_seen) as last_seen
                FROM kind_dvm_support
                GROUP BY kind
            ),
            latest_stats AS (
                SELECT DISTINCT ON (kind)
                    kind,
                    total_requests,
                    total_responses
                FROM kind_time_window_stats
                WHERE window_size = $3
                ORDER BY kind, timestamp DESC
            )
            SELECT 
                dc.kind,
                dc.last_seen,
                dc.num_supporting_dvms,
                s.total_requests,
                s.total_responses
            FROM dvm_counts dc
            JOIN active_kinds ak ON dc.kind = ak.kind
            LEFT JOIN latest_stats s ON s.kind = dc.kind
            ORDER BY dc.last_seen DESC
            LIMIT $1
            OFFSET $2
        """
        
        rows = await conn.fetch(query, limit, offset, timeRange.to_db_value())

        return {"kinds": [dict(row) for row in rows]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
