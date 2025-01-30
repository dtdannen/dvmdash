# api/src/main.py


from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import os
import asyncpg
from typing import Optional, List, Union
from enum import Enum
from fastapi import Query


class DVMTimeSeriesData(BaseModel):
    time: str
    total_responses: int
    total_feedback: int


class DVMStatsResponse(BaseModel):
    dvm_id: str
    timestamp: datetime
    total_responses: int
    total_feedback: int
    time_series: List[DVMTimeSeriesData]


class DVMListItem(BaseModel):
    id: str
    last_seen: datetime
    is_active: bool
    supported_kinds: List[int]
    total_responses: Optional[int] = None
    total_feedback: Optional[int] = None
    total_events: Optional[int] = None


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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_db_pool():
    return await asyncpg.create_pool(
        user=os.getenv("POSTGRES_USER", "devuser"),
        password=os.getenv("POSTGRES_PASSWORD", "devpass"),
        database=os.getenv("POSTGRES_DB", "dvmdash_pipeline"),
        host=os.getenv("POSTGRES_HOST", "postgres_pipeline"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
    )


@app.on_event("startup")
async def startup():
    app.state.pool = await get_db_pool()


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
            WITH first_timestamp AS (
                SELECT MIN(timestamp) as first_ts
                FROM time_window_stats
                WHERE window_size = $1
            ),
            timestamps AS (
                SELECT generate_series(
                    CASE 
                        WHEN $1 = '1 hour' THEN GREATEST(NOW() - INTERVAL '1 hour', (SELECT first_ts FROM first_timestamp))
                        WHEN $1 = '24 hours' THEN GREATEST(NOW() - INTERVAL '24 hours', (SELECT first_ts FROM first_timestamp))
                        WHEN $1 = '7 days' THEN GREATEST(NOW() - INTERVAL '7 days', (SELECT first_ts FROM first_timestamp))
                        WHEN $1 = '30 days' THEN GREATEST(NOW() - INTERVAL '30 days', (SELECT first_ts FROM first_timestamp))
                        ELSE (SELECT first_ts FROM first_timestamp)
                    END,
                    NOW(),
                    CASE 
                        WHEN $1 = '1 hour' THEN INTERVAL '5 minutes'
                        WHEN $1 = '24 hours' THEN INTERVAL '1 hour'
                        WHEN $1 = '7 days' THEN INTERVAL '6 hours'
                        WHEN $1 = '30 days' THEN INTERVAL '1 day'
                        ELSE INTERVAL '1 day'
                    END
                ) AS ts
            )
            SELECT 
                to_char(t.ts, 'YYYY-MM-DD HH24:MI:SS') as time,
                COALESCE(s.total_requests, 0) as total_requests,
                COALESCE(s.unique_users, 0) as unique_users,
                COALESCE(s.unique_dvms, 0) as unique_dvms
            FROM timestamps t
            LEFT JOIN time_window_stats s ON 
                date_trunc('hour', s.timestamp) = date_trunc('hour', t.ts)
                AND s.window_size = $1
            ORDER BY t.ts ASC
        """

        timeseries_rows = await conn.fetch(timeseries_query, timeRange.to_db_value())
        time_series = [dict(row) for row in timeseries_rows]

        # Combine all data
        resulting_data = {**dict(stats), "time_series": time_series}

        # print out the stats:
        # for k, v in resulting_data.items():
        #     if k != "time_series":
        #         print(f"{k}: {v}")
        #
        # for i in range(min(5, len(resulting_data["time_series"]))):
        #     print(resulting_data["time_series"][i])

        return resulting_data


@app.get("/api/dvms", response_model=DVMListResponse)
async def list_dvms(
    limit: int = Query(
        default=100, ge=1, le=1000, description="Number of DVMs to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of DVMs to skip"),
    timeRange: Optional[TimeWindow] = Query(
        default=None,
        alias="timeRange",
        description="Optional time window for stats",
    ),
):
    """
    Get a list of all DVMs we've ever seen with their supported kinds.
    Optionally includes stats for a specific time window.
    Returns DVMs ordered by last seen timestamp.
    """
    async with app.state.pool.acquire() as conn:
        base_query = """
            WITH dvm_kinds AS (
                SELECT 
                    dvm,
                    array_agg(kind ORDER BY kind) as supported_kinds
                FROM kind_dvm_support
                GROUP BY dvm
            )
        """

        if timeRange:
            query = base_query + """
                , latest_stats AS (
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
                    COALESCE(dk.supported_kinds, ARRAY[]::integer[]) as supported_kinds,
                    s.total_responses,
                    s.total_feedback,
                    (COALESCE(s.total_responses, 0) + COALESCE(s.total_feedback, 0)) as total_events
                FROM dvms d
                LEFT JOIN dvm_kinds dk ON dk.dvm = d.id
                LEFT JOIN latest_stats s ON s.dvm_id = d.id
                ORDER BY d.last_seen DESC
                LIMIT $1
                OFFSET $2
            """
            rows = await conn.fetch(query, limit, offset, timeRange.to_db_value())
        else:
            query = base_query + """
                SELECT 
                    d.id,
                    d.last_seen,
                    d.is_active,
                    COALESCE(dk.supported_kinds, ARRAY[]::integer[]) as supported_kinds,
                    NULL::integer as total_responses,
                    NULL::integer as total_feedback,
                    NULL::integer as total_events
                FROM dvms d
                LEFT JOIN dvm_kinds dk ON dk.dvm = d.id
                ORDER BY d.last_seen DESC
                LIMIT $1
                OFFSET $2
            """
            rows = await conn.fetch(query, limit, offset)

        return {"dvms": [dict(row) for row in rows]}


@app.get("/api/stats/dvm/{dvm_id}", response_model=DVMStatsResponse)
async def get_dvm_stats(
    dvm_id: str = Path(..., description="DVM ID"),
    timeRange: TimeWindow = Query(
        default=TimeWindow.ONE_MONTH,
        alias="timeRange",
        description="Time window for stats",
    ),
):
    async with app.state.pool.acquire() as conn:
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
        stats = await conn.fetchrow(stats_query, dvm_id, timeRange.to_db_value())

        if not stats:
            # Check if DVM exists
            dvm_check = await conn.fetchrow(
                "SELECT id, is_active FROM dvms WHERE id = $1", dvm_id
            )
            if not dvm_check:
                raise HTTPException(status_code=404, detail=f"DVM {dvm_id} not found")
            if not dvm_check["is_active"]:
                raise HTTPException(
                    status_code=404, detail=f"DVM {dvm_id} is no longer active"
                )
            # Return empty stats if DVM exists but has no data
            return {
                "dvm_id": dvm_id,
                "timestamp": datetime.now(),
                "total_responses": 0,
                "total_feedback": 0,
                "time_series": [],
            }

        timeseries_query = """
            WITH timestamps AS (
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
                ) AS ts
            )
            SELECT 
                to_char(t.ts, 'YYYY-MM-DD HH24:MI:SS') as time,
                COALESCE(s.total_responses, 0) as total_responses,
                COALESCE(s.total_feedback, 0) as total_feedback
            FROM timestamps t
            LEFT JOIN dvm_time_window_stats s ON 
                date_trunc('hour', s.timestamp) = date_trunc('hour', t.ts)
                AND s.dvm_id = $1
                AND s.window_size = $2
            ORDER BY t.ts ASC
        """

        timeseries_rows = await conn.fetch(
            timeseries_query, dvm_id, timeRange.to_db_value()
        )
        time_series = [dict(row) for row in timeseries_rows]

        return {**dict(stats), "time_series": time_series}


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
            WITH timestamps AS (
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
                ) AS ts
            )
            SELECT 
                to_char(t.ts, 'YYYY-MM-DD HH24:MI:SS') as time,
                COALESCE(s.total_requests, 0) as total_requests,
                COALESCE(s.total_responses, 0) as total_responses
            FROM timestamps t
            LEFT JOIN kind_time_window_stats s ON 
                date_trunc('hour', s.timestamp) = date_trunc('hour', t.ts)
                AND s.kind = $1
                AND s.window_size = $2
            ORDER BY t.ts ASC
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
    timeRange: Optional[TimeWindow] = Query(
        default=None,
        alias="timeRange",
        description="Optional time window for stats",
    ),
):
    """
    Get a list of all kinds we've ever seen with their supporting DVM counts.
    Returns kinds ordered by last seen timestamp.
    """
    async with app.state.pool.acquire() as conn:
        base_query = """
            WITH dvm_counts AS (
                SELECT 
                    kind,
                    COUNT(DISTINCT dvm) as num_supporting_dvms,
                    MAX(last_seen) as last_seen
                FROM kind_dvm_support
                GROUP BY kind
            )
        """

        if timeRange:
            query = base_query + """
                , latest_stats AS (
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
                LEFT JOIN latest_stats s ON s.kind = dc.kind
                ORDER BY dc.last_seen DESC
                LIMIT $1
                OFFSET $2
            """
            rows = await conn.fetch(query, limit, offset, timeRange.to_db_value())
        else:
            query = base_query + """
                SELECT 
                    kind,
                    last_seen,
                    num_supporting_dvms
                FROM dvm_counts
                ORDER BY last_seen DESC
                LIMIT $1
                OFFSET $2
            """
            rows = await conn.fetch(query, limit, offset)

        return {"kinds": [dict(row) for row in rows]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
