#!/usr/bin/env python3
import asyncio
import os
from typing import Dict, Optional
import requests
from loguru import logger

class BetterStackLogger:
    """Manages BetterStack logging setup"""
    
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.sources_created_ids = {}
        self.token = os.getenv("BETTERSTACK_TOKEN")
        if not self.token:
            raise ValueError("BETTERSTACK_TOKEN environment variable is required")
            
    def create_source(self, service_name: str) -> Optional[str]:
        """Create a log source for a service"""
        url = "https://telemetry.betterstack.com/api/v1/sources"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        payload = {
            "name": f"{self.project_name}-{service_name}",
            "platform": "rsyslog",
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json().get("data", {})
            attributes = data.get("attributes", {})
            
            if "token" in attributes:
                if "id" in data:
                    self.sources_created_ids[attributes["name"]] = data["id"]
                return attributes["token"]
                
        except Exception as e:
            logger.error(f"Failed to create BetterStack source: {str(e)}")
        return None
        
    def delete_sources(self):
        """Clean up all created log sources"""
        url = "https://telemetry.betterstack.com/api/v1/sources"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        for name, source_id in self.sources_created_ids.items():
            try:
                response = requests.delete(f"{url}/{source_id}", headers=headers)
                if response.status_code == 204:
                    logger.info(f"Deleted log source: {name}")
                else:
                    logger.error(f"Failed to delete log source: {name}")
            except Exception as e:
                logger.error(f"Error deleting log source {name}: {str(e)}")

class AppPlatformService:
    """Base class for App Platform services"""
    
    def __init__(self, do_token: str, project_name: str, name_prefix: str):
        self.token = do_token
        self.project_name = project_name
        self.name_prefix = name_prefix
        self.app_id = None
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
    async def transfer_to_project(self, project_id: str):
        """Transfer app to specified project"""
        if not self.app_id:
            raise ValueError("No app exists yet")
            
        try:
            transfer_response = requests.post(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}/transfer",
                headers=self.headers,
                json={"project_id": project_id}
            )
            transfer_response.raise_for_status()
            logger.info(f"Transferred {self.name_prefix} to project {project_id}")
        except Exception as e:
            logger.error(f"Failed to transfer {self.name_prefix} to project: {str(e)}")
            raise
            
    async def wait_for_app_ready(self):
        """Wait for App Platform application to be ready"""
        while True:
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            ).json()
            
            app = response.get("app", {})
            deployment = app.get("active_deployment", {})
            
            if deployment.get("phase") == "ACTIVE":
                logger.info(f"{self.name_prefix} is active")
                break
                
            await asyncio.sleep(10)
            
    async def cleanup(self):
        """Clean up App Platform resources"""
        if self.app_id:
            logger.info(f"Cleaning up {self.name_prefix}...")
            try:
                response = requests.delete(
                    f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                    headers=self.headers,
                )
                response.raise_for_status()
                logger.info(f"{self.name_prefix} cleaned up successfully")
            except Exception as e:
                logger.error(f"Failed to cleanup {self.name_prefix}: {str(e)}")

class EventCollector(AppPlatformService):
    """Manages Event Collector deployment"""
    
    def __init__(self, do_token: str, project_name: str, redis_config: Dict):
        super().__init__(do_token, project_name, "event-collector")
        self.redis_config = redis_config
        
    async def deploy(self, branch: str = "main", logs_token: Optional[str] = None, project_id: Optional[str] = None, frontend_url: Optional[str] = None):
        """Deploy Event Collector to App Platform"""
        logger.info(f"Deploying {self.name_prefix}...")
        
        app_spec = {
            "name": f"{self.project_name}-{self.name_prefix}",
            "region": "nyc",
            "workers": [
                {
                    "name": "worker",
                    "github": {
                        "repo": "dtdannen/dvmdash",
                        "branch": branch,
                        "deploy_on_push": False,
                    },
                    "source_dir": ".",
                    "instance_count": 1,
                    "instance_size_slug": "apps-d-2vcpu-8gb",
                    "dockerfile_path": "backend/event_collector/Dockerfile",
                    "envs": [
                        {
                            "key": "REDIS_URL",
                            "value": f"rediss://default:{self.redis_config['password']}@"
                                    f"{self.redis_config['host']}:{self.redis_config['port']}",
                            "type": "SECRET",
                        },
                        {
                            "key": "LOAD_HISTORICAL_DATA",
                            "value": "true",
                        },
                        {
                            "key": "TEST_DATA_BATCH_SIZE",
                            "value": "50000",
                        },
                        {
                            "key": "TEST_DATA_BATCH_DELAY",
                            "value": "0.0001",
                        },
                        {
                            "key": "START_LISTENING",
                            "value": "true",
                        },
                    ],
                }
            ],
        }
        
        # Add logging configuration if token provided
        if logs_token:
            app_spec["workers"][0]["log_destinations"] = [
                {
                    "name": "betterstack",
                    "logtail": {
                        "token": logs_token,
                    },
                }
            ]
            
        try:
            response = requests.post(
                "https://api.digitalocean.com/v2/apps",
                headers=self.headers,
                json={"spec": app_spec, "project_id": project_id} if project_id else {"spec": app_spec},
            )
            response.raise_for_status()
            
            app_data = response.json()["app"]
            self.app_id = app_data["id"]
            await self.wait_for_app_ready()
            
        except Exception as e:
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Failed to deploy {self.name_prefix}. API Response: {error_detail}")
                except:
                    logger.error(f"Failed to deploy {self.name_prefix}: {e.response.text}")
            else:
                logger.error(f"Failed to deploy {self.name_prefix}: {str(e)}")
            await self.cleanup()
            raise
            
    async def update_config(self, env_updates: Dict[str, str]):
        """Update environment variables for the service"""
        if not self.app_id:
            raise ValueError("No app exists yet")
            
        try:
            # Get current app spec
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            current_spec = response.json()["app"]["spec"]
            
            # Update environment variables
            for component in current_spec["workers"]:
                if component["name"] == "worker":
                    for env in component["envs"]:
                        if env["key"] in env_updates:
                            env["value"] = env_updates[env["key"]]
                    break
                    
            # Update the app
            response = requests.put(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
                json={"spec": current_spec},
            )
            response.raise_for_status()
            
            # Wait for update to complete
            await self.wait_for_app_ready()
            
        except Exception as e:
            logger.error(f"Failed to update {self.name_prefix} config: {str(e)}")
            raise

class BatchProcessor(AppPlatformService):
    """Manages Batch Processor deployment"""
    
    def __init__(
        self, 
        do_token: str, 
        project_name: str, 
        redis_config: Dict,
        postgres_config: Dict
    ):
        super().__init__(do_token, project_name, "batch-processor")
        self.redis_config = redis_config
        self.postgres_config = postgres_config
        self.current_instance_count = 0
        
    async def deploy(
        self, 
        branch: str = "main", 
        logs_token: Optional[str] = None,
        instance_count: int = 1,
        project_id: Optional[str] = None
    ):
        """Deploy Batch Processor to App Platform"""
        logger.info(f"Deploying {self.name_prefix}...")
        
        app_spec = {
            "name": f"{self.project_name}-{self.name_prefix}",
            "region": "nyc",
            "workers": [
                {
                    "name": "worker",
                    "github": {
                        "repo": "dtdannen/dvmdash",
                        "branch": branch,
                        "deploy_on_push": False,
                    },
                    "source_dir": ".",
                    "instance_count": instance_count,
                    "instance_size_slug": "apps-s-1vcpu-2gb",
                    "dockerfile_path": "backend/batch_processor/Dockerfile",
                    "envs": [
                        {
                            "key": "REDIS_URL",
                            "value": f"rediss://default:{self.redis_config['password']}@"
                                    f"{self.redis_config['host']}:{self.redis_config['port']}",
                            "type": "SECRET",
                        },
                        {
                            "key": "POSTGRES_USER",
                            "value": self.postgres_config["user"],
                        },
                        {
                            "key": "POSTGRES_PASSWORD",
                            "value": self.postgres_config["password"],
                            "type": "SECRET",
                        },
                        {
                            "key": "POSTGRES_DB",
                            "value": self.postgres_config["database"],
                        },
                        {
                            "key": "POSTGRES_HOST",
                            "value": self.postgres_config["host"],
                        },
                        {
                            "key": "POSTGRES_PORT",
                            "value": str(self.postgres_config["port"]),
                        },
                        {
                            "key": "MAX_WAIT_SECONDS",
                            "value": "3",
                        },
                        {
                            "key": "BATCH_SIZE",
                            "value": "10000",
                        },
                        {
                            "key": "BACKTEST_MODE",
                            "value": "true",
                        },
                    ],
                }
            ],
        }
        
        # Add logging configuration if token provided
        if logs_token:
            app_spec["workers"][0]["log_destinations"] = [
                {
                    "name": "betterstack",
                    "logtail": {
                        "token": logs_token,
                    },
                }
            ]
            
        try:
            response = requests.post(
                "https://api.digitalocean.com/v2/apps",
                headers=self.headers,
                json={"spec": app_spec, "project_id": project_id} if project_id else {"spec": app_spec},
            )
            response.raise_for_status()
            
            app_data = response.json()["app"]
            self.app_id = app_data["id"]
            self.current_instance_count = instance_count
            await self.wait_for_app_ready()
            
        except Exception as e:
            logger.error(f"Failed to deploy {self.name_prefix}: {str(e)}")
            await self.cleanup()
            raise
            
    async def scale(self, target_count: int):
        """Scale the number of batch processor instances"""
        if not self.app_id:
            raise ValueError("No batch processor app exists yet")
            
        if target_count <= self.current_instance_count:
            return
            
        logger.info(f"Scaling batch processors from {self.current_instance_count} to {target_count}...")
        
        try:
            # Get current app spec
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            current_spec = response.json()["app"]["spec"]
            
            # Update instance count
            for component in current_spec["workers"]:
                if component["name"] == "worker":
                    component["instance_count"] = target_count
                    break
                    
            # Update the app
            response = requests.put(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
                json={"spec": current_spec},
            )
            response.raise_for_status()
            
            # Wait for scaling to complete
            while True:
                status = requests.get(
                    f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                    headers=self.headers,
                ).json()
                
                app = status.get("app", {})
                deployment = app.get("active_deployment", {})
                
                if deployment.get("phase") == "ACTIVE":
                    for component in app.get("spec", {}).get("workers", []):
                        if (
                            component["name"] == "worker"
                            and component["instance_count"] == target_count
                        ):
                            logger.info(f"Successfully scaled to {target_count} instances")
                            self.current_instance_count = target_count
                            return
                            
                await asyncio.sleep(10)
                
        except Exception as e:
            logger.error(f"Failed to scale batch processors: {str(e)}")
            raise

class MonthlyArchiver(AppPlatformService):
    """Manages Monthly Archiver deployment"""
    
    def __init__(
        self, 
        do_token: str, 
        project_name: str, 
        redis_config: Dict,
        postgres_config: Dict
    ):
        super().__init__(do_token, project_name, "monthly-archiver")
        self.redis_config = redis_config
        self.postgres_config = postgres_config
        
    async def deploy(self, branch: str = "main", logs_token: Optional[str] = None, project_id: Optional[str] = None):
        """Deploy Monthly Archiver to App Platform"""
        logger.info(f"Deploying {self.name_prefix}...")
        
        app_spec = {
            "name": f"{self.project_name}-{self.name_prefix}",
            "region": "nyc",
            "workers": [
                {
                    "name": "worker",
                    "github": {
                        "repo": "dtdannen/dvmdash",
                        "branch": branch,
                        "deploy_on_push": False,
                    },
                    "source_dir": ".",
                    "instance_count": 1,
                    "instance_size_slug": "apps-s-1vcpu-0.5gb",
                    "dockerfile_path": "backend/monthly_archiver/Dockerfile",
                    "envs": [
                        {
                            "key": "REDIS_URL",
                            "value": f"rediss://default:{self.redis_config['password']}@"
                                    f"{self.redis_config['host']}:{self.redis_config['port']}",
                            "type": "SECRET",
                        },
                        {
                            "key": "POSTGRES_USER",
                            "value": self.postgres_config["user"],
                        },
                        {
                            "key": "POSTGRES_PASSWORD",
                            "value": self.postgres_config["password"],
                            "type": "SECRET",
                        },
                        {
                            "key": "POSTGRES_DB",
                            "value": self.postgres_config["database"],
                        },
                        {
                            "key": "POSTGRES_HOST",
                            "value": self.postgres_config["host"],
                        },
                        {
                            "key": "POSTGRES_PORT",
                            "value": str(self.postgres_config["port"]),
                        },
                        {
                            "key": "DAILY_CLEANUP_INTERVAL_SECONDS",
                            "value": "86400",  # 24 hours
                        },
                        {
                            "key": "MONTHLY_CLEANUP_BUFFER_DAYS",
                            "value": "3",
                        },
                        {
                            "key": "BATCH_PROCESSOR_GRACE_PERIOD_BEFORE_UPDATE_SECONDS",
                            "value": "15",
                        },
                    ],
                }
            ],
        }
        
        # Add logging configuration if token provided
        if logs_token:
            app_spec["workers"][0]["log_destinations"] = [
                {
                    "name": "betterstack",
                    "logtail": {
                        "token": logs_token,
                    },
                }
            ]
            
        try:
            response = requests.post(
                "https://api.digitalocean.com/v2/apps",
                headers=self.headers,
                json={"spec": app_spec, "project_id": project_id} if project_id else {"spec": app_spec},
            )
            response.raise_for_status()
            
            app_data = response.json()["app"]
            self.app_id = app_data["id"]
            await self.wait_for_app_ready()
            
        except Exception as e:
            logger.error(f"Failed to deploy {self.name_prefix}: {str(e)}")
            await self.cleanup()
            raise

class ApiService(AppPlatformService):
    """Manages API service deployment"""
    
    def __init__(self, do_token: str, project_name: str, postgres_config: Dict):
        super().__init__(do_token, project_name, "api")
        self.postgres_config = postgres_config
        
    async def deploy(self, branch: str = "main", logs_token: Optional[str] = None, project_id: Optional[str] = None):
        """Deploy API to App Platform"""
        logger.info(f"Deploying {self.name_prefix}...")
        
        app_spec = {
            "name": f"{self.project_name}-{self.name_prefix}",
            "region": "nyc",
            "services": [
                {
                    "name": "api",
                    "github": {
                        "repo": "dtdannen/dvmdash",
                        "branch": branch,
                        "deploy_on_push": False,
                    },
                    "source_dir": ".",
                    "instance_count": 1,
                    "instance_size_slug": "apps-s-1vcpu-1gb",
                    "dockerfile_path": "api/Dockerfile",
                    "http_port": 8000,
                    "health_check": {
                        "http_path": "/health",
                        "initial_delay_seconds": 10,
                        "period_seconds": 30
                    },
                    "envs": [
                        {
                            "key": "FRONTEND_URL",
                            "value": frontend_url or "${APP_DOMAIN}",
                        },
                        {
                            "key": "POSTGRES_USER",
                            "value": self.postgres_config["user"],
                        },
                        {
                            "key": "POSTGRES_PASSWORD",
                            "value": self.postgres_config["password"],
                            "type": "SECRET",
                        },
                        {
                            "key": "POSTGRES_DB",
                            "value": self.postgres_config["database"],
                        },
                        {
                            "key": "POSTGRES_HOST",
                            "value": self.postgres_config["host"],
                        },
                        {
                            "key": "POSTGRES_PORT",
                            "value": str(self.postgres_config["port"]),
                        },
                    ],
                }
            ],
        }
        
        # Add logging configuration if token provided
        if logs_token:
            app_spec["services"][0]["log_destinations"] = [
                {
                    "name": "betterstack",
                    "logtail": {
                        "token": logs_token,
                    },
                }
            ]
            
        try:
            response = requests.post(
                "https://api.digitalocean.com/v2/apps",
                headers=self.headers,
                json={"spec": app_spec, "project_id": project_id} if project_id else {"spec": app_spec},
            )
            response.raise_for_status()
            
            app_data = response.json()["app"]
            self.app_id = app_data["id"]
            await self.wait_for_app_ready()
            
        except Exception as e:
            logger.error(f"Failed to deploy {self.name_prefix}: {str(e)}")
            await self.cleanup()
            raise

class LandingPageService(AppPlatformService):
    """Manages Landing Page service deployment"""
    
    def __init__(self, do_token: str, project_name: str):
        super().__init__(do_token, project_name, "landing-page")
        self.app_url = None

    async def get_app_url(self) -> str:
        """Get the app's URL after deployment"""
        if not self.app_id:
            raise ValueError("No landing page app exists yet")
            
        try:
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            app_data = response.json()["app"]
            return f"https://{app_data.get('default_ingress', '')}"
        except Exception as e:
            logger.error(f"Failed to get landing page URL: {str(e)}")
            raise
        
    async def deploy(self, branch: str = "main", logs_token: Optional[str] = None, project_id: Optional[str] = None) -> str:
        """Deploy Landing Page to App Platform"""
        logger.info(f"Deploying {self.name_prefix}...")
        
        app_spec = {
            "name": f"{self.project_name}-{self.name_prefix}",
            "region": "nyc",
            "services": [
                {
                    "name": "landing-page",
                    "github": {
                        "repo": "dtdannen/dvmdash",
                        "branch": branch,
                        "deploy_on_push": False,
                    },
                    "source_dir": "landing_page",
                    "instance_count": 1,
                    "instance_size_slug": "apps-s-1vcpu-1gb",
                    "dockerfile_path": "landing_page/Dockerfile",
                    "http_port": 3000,
                    "health_check": {
                        "http_path": "/",
                        "initial_delay_seconds": 10,
                        "period_seconds": 30
                    },
                    "routes": [
                        {
                            "path": "/",
                            "preserve_path_prefix": False
                        }
                    ],
                    "envs": [
                        {
                            "key": "NODE_ENV",
                            "value": "production"
                        },
                        {
                            "key": "PORT",
                            "value": "3000"
                        },
                        {
                            "key": "NPM_CONFIG_PRODUCTION",
                            "value": "true",
                            "scope": "BUILD_TIME"
                        },
                        {
                            "key": "NEXT_TELEMETRY_DISABLED",
                            "value": "1",
                            "scope": "BUILD_TIME"
                        },
                        {
                            "key": "NEXT_SHARP_PATH",
                            "value": "/workspace/node_modules/sharp",
                            "scope": "BUILD_TIME"
                        }
                    ]
                }
            ],
        }
        
        # Add logging configuration if token provided
        if logs_token:
            app_spec["services"][0]["log_destinations"] = [
                {
                    "name": "betterstack",
                    "logtail": {
                        "token": logs_token,
                    },
                }
            ]
            
        try:
            # Deploy the app
            logger.info("Creating app deployment...")
            deploy_payload = {"spec": app_spec}
            if project_id:
                deploy_payload["project_id"] = project_id
                
            response = requests.post(
                "https://api.digitalocean.com/v2/apps",
                headers=self.headers,
                json=deploy_payload,
            )
            
            response_data = response.json()
            logger.info(f"Deployment response status: {response.status_code}")
            logger.info(f"Full response data: {response_data}")
            
            if response.status_code not in [200, 201]:
                error_data = response_data
                logger.error(f"Deployment failed with status {response.status_code}:")
                if "message" in error_data:
                    logger.error(f"Error message: {error_data['message']}")
                if "error" in error_data:
                    logger.error(f"Error details: {error_data['error']}")
                raise ValueError(f"Failed to create app: {error_data.get('message', 'Unknown error')}")
                
            if "app" not in response_data:
                logger.error("Response data does not contain 'app' key")
                logger.error(f"Full response data: {response_data}")
                raise ValueError("Invalid response format: missing 'app' data")
            
            app_data = response.json()["app"]
            self.app_id = app_data["id"]
            
            # Get and store the assigned URL
            self.app_url = await self.get_app_url()
            logger.info(f"Landing page assigned URL: {self.app_url}")
            
            # Monitor deployment progress
            logger.info("Monitoring deployment progress...")
            while True:
                status = requests.get(
                    f"https://api.digitalocean.com/v2/apps/{self.app_id}/deployments",
                    headers=self.headers,
                ).json()
                
                if "deployments" not in status or not status["deployments"]:
                    await asyncio.sleep(10)
                    continue
                
                latest_deployment = status["deployments"][0]
                phase = latest_deployment.get("phase", "")
                logger.info(f"Deployment phase: {phase}")
                
                if phase == "ACTIVE":
                    logger.info("Deployment completed successfully!")
                    break
                elif phase in ["ERROR", "FAILED", "CANCELED"]:
                    logger.error(f"Deployment failed in phase {phase}")
                    if "progress" in latest_deployment:
                        for step in latest_deployment["progress"].get("steps", []):
                            if step.get("status") == "ERROR":
                                logger.error(f"Step '{step.get('name')}' failed: {step.get('message')}")
                    raise ValueError(f"Deployment failed in phase {phase}")
                
                await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Failed to deploy {self.name_prefix}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"API Response: {error_detail}")
                    if "error" in error_detail:
                        logger.error(f"Error message: {error_detail['error'].get('message', '')}")
                        logger.error(f"Error code: {error_detail['error'].get('code', '')}")
                except:
                    logger.error(f"Raw response: {e.response.text}")
            await self.cleanup()
            raise ValueError(f"Deployment failed: {str(e)}")


class FrontendService(AppPlatformService):
    """Manages Frontend service deployment"""
    
    def __init__(self, do_token: str, project_name: str):
        super().__init__(do_token, project_name, "frontend")
        self.app_url = None

    async def get_app_url(self) -> str:
        """Get the app's URL after deployment"""
        if not self.app_id:
            raise ValueError("No frontend app exists yet")
            
        try:
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            app_data = response.json()["app"]
            return f"https://{app_data.get('default_ingress', '')}"
        except Exception as e:
            logger.error(f"Failed to get frontend URL: {str(e)}")
            raise
        
    async def deploy(self, branch: str = "main", logs_token: Optional[str] = None, project_id: Optional[str] = None) -> str:
        """Deploy Frontend to App Platform"""
        logger.info(f"Deploying {self.name_prefix}...")
        
        app_spec = {
            "name": f"{self.project_name}-{self.name_prefix}",
            "region": "nyc",
            "services": [
                {
                    "name": "frontend",
                    "github": {
                        "repo": "dtdannen/dvmdash",
                        "branch": branch,
                        "deploy_on_push": False,
                    },
                    "source_dir": "frontend/dvmdash-frontend",
                    "instance_count": 1,
                    "instance_size_slug": "apps-s-1vcpu-1gb",
                    "dockerfile_path": "frontend/dvmdash-frontend/Dockerfile",
                    "http_port": 3000,
                    "health_check": {
                        "http_path": "/",
                        "initial_delay_seconds": 10,
                        "period_seconds": 30
                    },
                    "routes": [
                        {
                            "path": "/",
                            "preserve_path_prefix": False
                        }
                    ],
                    "envs": [
                        {
                            "key": "NEXT_PUBLIC_API_URL",
                            "value": "https://dvmdash-prod-api-lh4pf.ondigitalocean.app",
                        },
                        {
                            "key": "APP_DOMAIN",
                            "value": "${APP_DOMAIN}",
                        },
                        {
                            "key": "NODE_ENV",
                            "value": "production"
                        },
                        {
                            "key": "PORT",
                            "value": "3000"
                        },
                        {
                            "key": "NPM_CONFIG_PRODUCTION",
                            "value": "true",
                            "scope": "BUILD_TIME"
                        },
                        {
                            "key": "NEXT_TELEMETRY_DISABLED",
                            "value": "1",
                            "scope": "BUILD_TIME"
                        },
                        {
                            "key": "NEXT_SHARP_PATH",
                            "value": "/workspace/node_modules/sharp",
                            "scope": "BUILD_TIME"
                        }
                    ],
                    "log_destinations": [
                        {
                            "name": "betterstack",
                            "logtail": {
                                "token": logs_token,
                            },
                        }
                    ] if logs_token else [],
                }
            ],
        }
        
        # Add logging configuration if token provided
        if logs_token:
            app_spec["services"][0]["log_destinations"] = [
                {
                    "name": "betterstack",
                    "logtail": {
                        "token": logs_token,
                    },
                }
            ]
            
        try:
            # Deploy the app
            logger.info("Creating app deployment...")
            deploy_payload = {"spec": app_spec}
            if project_id:
                deploy_payload["project_id"] = project_id
                
            response = requests.post(
                "https://api.digitalocean.com/v2/apps",
                headers=self.headers,
                json=deploy_payload,
            )
            
            response_data = response.json()
            logger.info(f"Deployment response status: {response.status_code}")
            logger.info(f"Full response data: {response_data}")
            
            if response.status_code not in [200, 201]:
                error_data = response_data
                logger.error(f"Deployment failed with status {response.status_code}:")
                if "message" in error_data:
                    logger.error(f"Error message: {error_data['message']}")
                if "error" in error_data:
                    logger.error(f"Error details: {error_data['error']}")
                raise ValueError(f"Failed to create app: {error_data.get('message', 'Unknown error')}")
                
            if "app" not in response_data:
                logger.error("Response data does not contain 'app' key")
                logger.error(f"Full response data: {response_data}")
                raise ValueError("Invalid response format: missing 'app' data")
            
            app_data = response.json()["app"]
            self.app_id = app_data["id"]
            
            # Get and store the assigned URL
            self.app_url = await self.get_app_url()
            logger.info(f"Frontend assigned URL: {self.app_url}")
            
            # Monitor deployment progress
            logger.info("Monitoring deployment progress...")
            while True:
                status = requests.get(
                    f"https://api.digitalocean.com/v2/apps/{self.app_id}/deployments",
                    headers=self.headers,
                ).json()
                
                if "deployments" not in status or not status["deployments"]:
                    await asyncio.sleep(10)
                    continue
                
                latest_deployment = status["deployments"][0]
                phase = latest_deployment.get("phase", "")
                logger.info(f"Deployment phase: {phase}")
                
                if phase == "ACTIVE":
                    logger.info("Deployment completed successfully!")
                    break
                elif phase in ["ERROR", "FAILED", "CANCELED"]:
                    logger.error(f"Deployment failed in phase {phase}")
                    if "progress" in latest_deployment:
                        for step in latest_deployment["progress"].get("steps", []):
                            if step.get("status") == "ERROR":
                                logger.error(f"Step '{step.get('name')}' failed: {step.get('message')}")
                    raise ValueError(f"Deployment failed in phase {phase}")
                
                await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"Failed to deploy {self.name_prefix}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"API Response: {error_detail}")
                    if "error" in error_detail:
                        logger.error(f"Error message: {error_detail['error'].get('message', '')}")
                        logger.error(f"Error code: {error_detail['error'].get('code', '')}")
                except:
                    logger.error(f"Raw response: {e.response.text}")
            await self.cleanup()
            raise ValueError(f"Deployment failed: {str(e)}")
