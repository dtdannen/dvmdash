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
    ONE_HOUR = "1 hour"
    ONE_DAY = "24 hours"
    ONE_WEEK = "7 days"
    ONE_MONTH = "30 days"
    ALL_TIME = "all time"


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
    window: TimeWindow = Query(
        default=TimeWindow.ALL_TIME,
        description=f"Time window for stats should be one of: {', '.join(TimeWindow.__members__)}",
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
        row = await conn.fetchrow(query, window)

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No global stats found for window size {window}",
            )

        return dict(row)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
