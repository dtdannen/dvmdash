"""
This is a temporary fix for the relay management API endpoints.
It adds new routes that use query parameters instead of path parameters for relay URLs.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from typing import Dict, Optional, Any

from relay_config import RelayConfigManager

router = APIRouter(prefix="/api/admin")

@router.delete("/relay")
async def remove_relay_by_query(request: Request, url: str = Query(..., description="Relay URL to remove")):
    """Remove a relay from the configuration using a query parameter"""
    print(f"Removing relay by query parameter: {url}")
    
    redis_client = request.app.state.redis
    success = RelayConfigManager.remove_relay(redis_client, url)
    
    if success:
        # Request relay redistribution from coordinator
        RelayConfigManager.request_relay_distribution(redis_client)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Relay not found")

@router.put("/relay/activity")
async def update_relay_activity_by_query(
    request: Request, 
    url: str = Query(..., description="Relay URL to update"),
    activity: str = Query(..., description="New activity level (high or normal)")
):
    """Update a relay's activity level using query parameters"""
    if activity not in ["high", "normal"]:
        raise HTTPException(status_code=400, detail="Invalid activity level")
    
    print(f"Updating relay activity by query parameter: {url} to {activity}")
    
    redis_client = request.app.state.redis
    success = RelayConfigManager.update_relay_activity(redis_client, url, activity)
    
    if success:
        # Request relay redistribution from coordinator
        RelayConfigManager.request_relay_distribution(redis_client)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Relay not found")
