# api/src/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import os
import asyncpg
from typing import Optional, List
from enum import Enum
from fastapi import Query


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
