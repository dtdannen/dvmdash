# api/src/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import os
import asyncpg
from typing import Optional


class GlobalStatsResponse(BaseModel):
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    period_requests: int
    period_responses: int
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
async def get_latest_global_stats():
    async with app.state.pool.acquire() as conn:
        query = """
            SELECT * FROM global_stats_rollups 
            ORDER BY timestamp DESC 
            LIMIT 1
        """
        row = await conn.fetchrow(query)

        if not row:
            raise HTTPException(status_code=404, detail="No global stats found")

        return dict(row)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
