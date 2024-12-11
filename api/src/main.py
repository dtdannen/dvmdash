# api/src/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import os
import asyncpg
from typing import Optional
from enum import Enum
from fastapi import Query


class TimeWindow(str, Enum):
    ONE_HOUR = "1h"
    ONE_DAY = "24h"
    ONE_WEEK = "7d"
    ONE_MONTH = "30d"
    ALL_TIME = "all"

    def to_db_value(self) -> str:
        """Convert frontend time window to database value"""
        mapping = {
            "1h": "1 hour",
            "24h": "24 hours",
            "7d": "7 days",
            "30d": "30 days",
            "all": "all time",
        }
        return mapping[self.value]


class GlobalStatsResponse(BaseModel):
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    running_total_requests: int
    running_total_responses: int
    running_total_unique_dvms: int
    running_total_unique_kinds: int
    running_total_unique_users: int
    most_popular_dvm: Optional[str]
    most_popular_kind: Optional[int]
    most_competitive_kind: Optional[int]


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
        default=TimeWindow.ALL_TIME,
        alias="timeRange",  # Match the frontend parameter name
        description="Time window for stats",
    )
):
    async with app.state.pool.acquire() as conn:
        query = """
            SELECT 
                timestamp,
                period_start,
                period_end,
                total_requests as running_total_requests,
                total_responses as running_total_responses,
                unique_users as running_total_unique_users,
                unique_kinds as running_total_unique_kinds,
                unique_dvms as running_total_unique_dvms,
                popular_dvm as most_popular_dvm,
                popular_kind as most_popular_kind,
                competitive_kind as most_competitive_kind
            FROM time_window_stats 
            WHERE window_size = $1
            ORDER BY timestamp DESC 
            LIMIT 1
        """
        row = await conn.fetchrow(query, timeRange.to_db_value())

        print(f"row is {row}")

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No global stats found for window size {timeRange}",
            )

        return dict(row)


@app.get("/api/stats/global/timeseries")
async def get_global_stats_timeseries(
    timeRange: TimeWindow = Query(
        default=TimeWindow.ALL_TIME,
        alias="timeRange",
        description="Time window for stats",
    )
):
    async with app.state.pool.acquire() as conn:
        # Calculate the start time based on the time range
        window_mapping = {
            "1h": "NOW() - INTERVAL '1 hour'",
            "24h": "NOW() - INTERVAL '24 hours'",
            "7d": "NOW() - INTERVAL '7 days'",
            "30d": "NOW() - INTERVAL '30 days'",
            "all": "timestamp '1970-01-01'",  # Or some reasonable start date
        }

        query = """
            WITH time_series AS (
                SELECT 
                    timestamp,
                    total_requests,
                    total_responses,
                    unique_dvms,
                    unique_kinds,
                    unique_users
                FROM time_window_stats 
                WHERE 
                    window_size = $1
                    AND timestamp >= {}
                ORDER BY timestamp ASC
            )
            SELECT * FROM time_series
        """.format(
            window_mapping[timeRange.value]
        )

        rows = await conn.fetch(query, timeRange.to_db_value())

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No time series data found for window size {timeRange}",
            )

        return [dict(row) for row in rows]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
