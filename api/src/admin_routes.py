from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import redis
import docker
import os
from datetime import datetime

from .relay_config import RelayConfigManager

router = APIRouter(prefix="/api/admin")

# Environment variables
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(REDIS_URL)

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
async def get_relays():
    """Get all configured relays with their settings and metrics"""
    try:
        relays = RelayConfigManager.get_all_relays(redis_client)
        result = []
        
        for url, config in relays.items():
            # Get metrics from all collectors for this relay
            metrics = {}
            collectors = redis_client.smembers('dvmdash:collectors:active')
            for collector_id in collectors:
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
async def add_relay(relay: RelayConfig):
    """Add a new relay to the configuration"""
    success = RelayConfigManager.add_relay(redis_client, relay.url, relay.activity)
    if success:
        # Trigger relay redistribution
        RelayConfigManager.distribute_relays(redis_client)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Relay already exists")

@router.put("/relays/{relay_url}/activity")
async def update_relay_activity(relay_url: str, activity: str):
    """Update a relay's activity level"""
    if activity not in ["high", "normal"]:
        raise HTTPException(status_code=400, detail="Invalid activity level")
    
    success = RelayConfigManager.update_relay_activity(redis_client, relay_url, activity)
    if success:
        # Trigger relay redistribution
        RelayConfigManager.distribute_relays(redis_client)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Relay not found")

@router.delete("/relays/{relay_url}")
async def remove_relay(relay_url: str):
    """Remove a relay from the configuration"""
    success = RelayConfigManager.remove_relay(redis_client, relay_url)
    if success:
        # Trigger relay redistribution
        RelayConfigManager.distribute_relays(redis_client)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Relay not found")

@router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """Get overall system status including collectors and configuration"""
    try:
        collectors = redis_client.smembers('dvmdash:collectors:active')
        collector_info = []
        
        for collector_id in collectors:
            heartbeat = redis_client.get(f'dvmdash:collector:{collector_id}:heartbeat')
            config_version = redis_client.get(f'dvmdash:collector:{collector_id}:config_version')
            relays = redis_client.get(f'dvmdash:collector:{collector_id}:relays')
            
            collector_info.append(CollectorInfo(
                id=collector_id,
                last_heartbeat=int(heartbeat) if heartbeat else None,
                config_version=int(config_version) if config_version else None,
                relays=list(relays.keys()) if relays else []
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
async def reboot_collectors():
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
