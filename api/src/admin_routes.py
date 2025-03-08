from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import docker
import os
import json
import time
from datetime import datetime

from relay_config import RelayConfigManager

router = APIRouter(prefix="/api/admin")

# Helper function to request relay distribution from the coordinator
def request_relay_distribution(redis_client):
    """
    Set a flag in Redis to request relay distribution from the coordinator.
    This is more robust than directly triggering distribution from the API.
    """
    # Set the last_change timestamp to trigger redistribution
    redis_client.set('dvmdash:settings:last_change', int(time.time()))
    # Optionally set a specific flag if needed
    redis_client.set('dvmdash:settings:distribution_requested', '1', ex=300)  # Expire after 5 minutes
    return True

# Models
class RelayConfig(BaseModel):
    url: str
    activity: str = "normal"

class RelayInfo(BaseModel):
    url: str
    activity: str
    added_at: int
    added_by: str
    metrics: Optional[Dict] = None

class CollectorInfo(BaseModel):
    id: str
    last_heartbeat: Optional[int] = None
    config_version: Optional[int] = None
    relays: List[str] = []

class SystemStatus(BaseModel):
    collectors: List[CollectorInfo]
    outdated_collectors: List[str]
    config_version: int
    last_change: Optional[int] = None

@router.get("/relays", response_model=List[RelayInfo])
async def get_relays(request: Request):
    """Get all configured relays with their settings and metrics"""
    try:
        redis_client = request.app.state.redis
        relays = RelayConfigManager.get_all_relays(redis_client)
        result = []
        
        # Get current time in seconds
        current_time = int(time.time())
        # Consider collectors active if they've sent a heartbeat in the last 5 minutes
        active_threshold = current_time - (5 * 60)
        
        for url, config in relays.items():
            # Get metrics from all collectors for this relay
            metrics = {}
            collectors = redis_client.smembers('dvmdash:collectors:active')
            for collector_id in collectors:
                # Include metrics from all collectors, even if they haven't sent a heartbeat yet
                metrics_key = f'dvmdash:collector:{collector_id}:metrics:{url}'
                collector_metrics = redis_client.hgetall(metrics_key)
                if collector_metrics:
                    metrics[collector_id] = collector_metrics
            
            result.append(RelayInfo(
                url=url,
                activity=config["activity"],
                added_at=config["added_at"],
                added_by=config["added_by"],
                metrics=metrics if metrics else None
            ))
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/relays")
async def add_relay(relay: RelayConfig, request: Request):
    """Add a new relay to the configuration"""
    redis_client = request.app.state.redis
    success = RelayConfigManager.add_relay(redis_client, relay.url, relay.activity)
    if success:
        # Request relay redistribution from coordinator
        request_relay_distribution(redis_client)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Relay already exists")

@router.put("/relays/{relay_url}/activity")
async def update_relay_activity(relay_url: str, activity: str, request: Request):
    """Update a relay's activity level"""
    if activity not in ["high", "normal"]:
        raise HTTPException(status_code=400, detail="Invalid activity level")
    
    redis_client = request.app.state.redis
    success = RelayConfigManager.update_relay_activity(redis_client, relay_url, activity)
    if success:
        # Request relay redistribution from coordinator
        request_relay_distribution(redis_client)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Relay not found")

@router.delete("/relays/{relay_url}")
async def remove_relay(relay_url: str, request: Request):
    """Remove a relay from the configuration"""
    redis_client = request.app.state.redis
    success = RelayConfigManager.remove_relay(redis_client, relay_url)
    if success:
        # Request relay redistribution from coordinator
        request_relay_distribution(redis_client)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Relay not found")

@router.get("/status", response_model=SystemStatus)
async def get_system_status(request: Request):
    """Get overall system status including collectors and configuration"""
    try:
        redis_client = request.app.state.redis
        collectors = redis_client.smembers('dvmdash:collectors:active')
        collector_info = []
        
        # Get current time in seconds
        current_time = int(time.time())
        # Consider collectors active if they've sent a heartbeat in the last 5 minutes
        active_threshold = current_time - (5 * 60)
        
        for collector_id in collectors:
            heartbeat = redis_client.get(f'dvmdash:collector:{collector_id}:heartbeat')
            config_version = redis_client.get(f'dvmdash:collector:{collector_id}:config_version')
            relays_json = redis_client.get(f'dvmdash:collector:{collector_id}:relays')
            
            # Include all collectors in the active set, even if they haven't sent a heartbeat yet
            # This ensures newly started collectors are visible in the admin page
            
            relays_list = []
            if relays_json:
                try:
                    relays_dict = json.loads(relays_json)
                    relays_list = list(relays_dict.keys())
                except json.JSONDecodeError:
                    print(f"Error decoding relays JSON for collector {collector_id}: {relays_json}")
            
            collector_info.append(CollectorInfo(
                id=collector_id,
                last_heartbeat=int(heartbeat) if heartbeat else None,
                config_version=int(config_version) if config_version else None,
                relays=relays_list
            ))
        
        config_version = redis_client.get('dvmdash:settings:config_version')
        last_change = redis_client.get('dvmdash:settings:last_change')
        outdated = RelayConfigManager.get_outdated_collectors(redis_client)
        
        return SystemStatus(
            collectors=collector_info,
            outdated_collectors=outdated,
            config_version=int(config_version) if config_version else 0,
            last_change=int(last_change) if last_change else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collectors/reboot")
async def reboot_collectors(request: Request):
    """Reboot all event collectors"""
    try:
        # For local development, use Docker API
        if os.getenv("ENVIRONMENT") == "development":
            client = docker.from_env()
            containers = client.containers.list(
                filters={"label": "com.docker.compose.service=event_collector"}
            )
            for container in containers:
                container.restart()
        else:
            # For production, use DigitalOcean API via existing deploy script
            from deploy.production_deploy import restart_event_collectors
            await restart_event_collectors()
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collectors")
async def add_collector(request: Request):
    """Add a new event collector instance"""
    try:
        # For local development, use Docker API
        if os.getenv("ENVIRONMENT") == "development":
            client = docker.from_env()
            container = client.containers.run(
                "dvmdash-event-collector",
                detach=True,
                environment={"START_LISTENING": "true"},
                labels={"com.docker.compose.service": "event_collector"}
            )
            return {"status": "success", "container_id": container.id}
        else:
            # For production, use DigitalOcean API
            from deploy.production_deploy import add_event_collector
            result = await add_event_collector()
            return {"status": "success", "details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/collectors/{collector_id}")
async def remove_collector(collector_id: str, request: Request):
    """Remove a specific event collector"""
    try:
        redis_client = request.app.state.redis
        
        # Remove from active set
        redis_client.srem('dvmdash:collectors:active', collector_id)
        
        # Clean up all collector keys
        for key in redis_client.keys(f'dvmdash:collector:{collector_id}:*'):
            redis_client.delete(key)
            
        # Request relay redistribution from coordinator
        request_relay_distribution(redis_client)
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/debug/redis")
async def get_redis_debug(request: Request):
    """Get Redis state for debugging"""
    try:
        redis_client = request.app.state.redis
        result: Dict[str, Any] = {
            "collectors": {},
            "config": {}
        }
        
        # Get collector information
        collectors = redis_client.smembers('dvmdash:collectors:active')
        for collector_id in collectors:
            result["collectors"][collector_id] = {
                "heartbeat": redis_client.get(f'dvmdash:collector:{collector_id}:heartbeat'),
                "config_version": redis_client.get(f'dvmdash:collector:{collector_id}:config_version'),
                "relays": json.loads(redis_client.get(f'dvmdash:collector:{collector_id}:relays') or '{}')
            }
            
            # Get metrics for each relay
            result["collectors"][collector_id]["metrics"] = {}
            for relay_url in result["collectors"][collector_id]["relays"].keys():
                metrics_key = f'dvmdash:collector:{collector_id}:metrics:{relay_url}'
                metrics = redis_client.hgetall(metrics_key)
                if metrics:
                    result["collectors"][collector_id]["metrics"][relay_url] = metrics
        
        # Get configuration
        result["config"]["relays"] = json.loads(redis_client.get('dvmdash:settings:relays') or '{}')
        result["config"]["config_version"] = redis_client.get('dvmdash:settings:config_version')
        result["config"]["last_change"] = redis_client.get('dvmdash:settings:last_change')
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
