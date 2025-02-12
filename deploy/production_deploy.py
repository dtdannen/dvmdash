#!/usr/bin/env python3
import asyncio
import argparse
import os
import signal
import sys
from typing import Dict, List, Optional, Tuple
import aioconsole  # For async console input
import requests
import asyncpg
import redis.asyncio as redis
from loguru import logger
from dotenv import load_dotenv
from production_components import (
    BetterStackLogger,
    EventCollector,
    BatchProcessor,
    MonthlyArchiver,
    ApiService,
    FrontendService,
)

# Load environment variables
load_dotenv()

# Constants
NUM_BATCH_PROCESSORS = 5

# Global shutdown event
shutdown_event = asyncio.Event()

async def confirm_stage(stage_name: str, details: Dict[str, str]) -> Tuple[bool, bool]:
    """
    Display stage completion details and wait for user confirmation.
    Returns a tuple of (continue, destroy):
        - continue: True to continue deployment, False to stop
        - destroy: True to destroy infrastructure, False to keep it
    """
    logger.info(f"\n=== {stage_name} Complete ===")
    logger.info("Deployed resources:")
    for resource, status in details.items():
        logger.info(f"  • {resource}: {status}")
    
    logger.info("\nPlease verify the infrastructure is correctly provisioned.")
    response = await aioconsole.ainput("\nPress Enter to continue, 'abort' to quit without destroying, or 'destroy' to remove infrastructure: ")
    response = response.lower().strip()
    
    if not response:
        return True, False  # Continue deployment
    elif response == 'destroy':
        return False, True  # Stop and destroy
    else:
        return False, False  # Stop without destroying

class PostgresManager:
    """Manages PostgreSQL database provisioning and configuration"""
    
    def __init__(self, do_token: str, project_name: str, name_prefix: str = "pipeline"):
        self.token = do_token
        self.project_name = project_name
        self.name_prefix = name_prefix
        self.db_id = None
        self.db_config = None
        self.pool = None

    async def _init_db_pool(self):
        """Initialize database connection pool"""
        self.pool = await asyncpg.create_pool(**self.db_config)
        
    async def provision(self, project_id: str = None) -> Dict:
        """Provision and configure PostgreSQL database"""
        logger.info(f"Creating managed Postgres database ({self.name_prefix})...")
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
        create_params = {
            "name": f"{self.project_name}-{self.name_prefix}",
            "engine": "pg",
            "version": "16",
            "size": "db-s-1vcpu-2gb",
            "region": "nyc1",
            "num_nodes": 1,
        }
        
        if project_id:
            create_params["project_id"] = project_id
            
        try:
            response = requests.post(
                "https://api.digitalocean.com/v2/databases",
                headers=headers,
                json=create_params,
            )
            response.raise_for_status()
            self.db_id = response.json()["database"]["id"]
            
            # Wait for database to be ready
            logger.info("Waiting for database to be ready...")
            while True:
                if shutdown_event.is_set():
                    raise Exception("Received shutdown signal during database provisioning")
                    
                status = requests.get(
                    f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                    headers=headers,
                ).json()["database"]["status"]
                
                if status == "online":
                    break
                await asyncio.sleep(10)
                
            # Get connection details
            db_info = requests.get(
                f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                headers=headers,
            ).json()["database"]
            
            self.db_config = {
                "host": db_info["connection"]["host"],
                "port": db_info["connection"]["port"],
                "database": "defaultdb",
                "user": db_info["connection"]["user"],
                "password": db_info["connection"]["password"],
            }
            
            # Initialize database pool
            await self._init_db_pool()
            
            # Initialize schema
            logger.info("Initializing database schema...")
            with open("infrastructure/postgres/pipeline_init.sql", "r") as f:
                schema = f.read()
                
            async with self.pool.acquire() as conn:
                await conn.execute(schema)
                
            logger.info(f"PostgreSQL database setup complete!")
            return self.db_config
            
        except Exception as e:
            logger.error(f"Failed to provision PostgreSQL: {str(e)}")
            await self.cleanup()
            raise
            
    async def cleanup(self):
        """Clean up database resources"""
        if self.pool:
            await self.pool.close()
            
        if self.db_id:
            logger.info("Cleaning up PostgreSQL database...")
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            try:
                response = requests.delete(
                    f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                    headers=headers,
                )
                response.raise_for_status()
                logger.info("PostgreSQL database cleaned up successfully")
            except Exception as e:
                logger.error(f"Failed to cleanup PostgreSQL: {str(e)}")

class RedisManager:
    """Manages Redis database provisioning and configuration"""
    
    def __init__(self, do_token: str, project_name: str):
        self.token = do_token
        self.project_name = project_name
        self.db_id = None
        self.db_config = None
        self.redis_client = None

    async def _init_redis_client(self):
        """Initialize Redis client with the managed database connection details"""
        self.redis_client = redis.Redis(
            host=self.db_config["host"],
            port=self.db_config["port"],
            password=self.db_config["password"],
            ssl=True,
            decode_responses=True,
        )
        # Test the connection
        await self.redis_client.ping()
        
    async def provision(self, project_id: str = None) -> Dict:
        """Provision and configure Redis database"""
        logger.info("Creating managed Redis database...")
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
        create_params = {
            "name": f"{self.project_name}-redis",
            "engine": "redis",
            "version": "7",
            "size": "db-s-1vcpu-2gb",
            "region": "nyc1",
            "num_nodes": 1,
        }
        
        if project_id:
            create_params["project_id"] = project_id
            
        try:
            response = requests.post(
                "https://api.digitalocean.com/v2/databases",
                headers=headers,
                json=create_params,
            )
            response.raise_for_status()
            self.db_id = response.json()["database"]["id"]
            
            # Wait for database to be ready
            logger.info("Waiting for Redis database to be ready...")
            while True:
                if shutdown_event.is_set():
                    raise Exception("Received shutdown signal during Redis provisioning")
                    
                status = requests.get(
                    f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                    headers=headers,
                ).json()["database"]["status"]
                
                if status == "online":
                    break
                await asyncio.sleep(10)
                
            # Get connection details
            db_info = requests.get(
                f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                headers=headers,
            ).json()["database"]
            
            self.db_config = {
                "host": db_info["connection"]["host"],
                "port": db_info["connection"]["port"],
                "password": db_info["connection"]["password"],
            }
            
            # Initialize and test Redis client
            await self._init_redis_client()
            
            logger.info("Redis database setup complete!")
            return self.db_config
            
        except Exception as e:
            logger.error(f"Failed to provision Redis: {str(e)}")
            await self.cleanup()
            raise
            
    async def cleanup(self):
        """Clean up database resources"""
        if self.redis_client:
            await self.redis_client.close()
            
        if self.db_id:
            logger.info("Cleaning up Redis database...")
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            try:
                response = requests.delete(
                    f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                    headers=headers,
                )
                response.raise_for_status()
                logger.info("Redis database cleaned up successfully")
            except Exception as e:
                logger.error(f"Failed to cleanup Redis: {str(e)}")

class DeploymentManager:
    """Manages the entire deployment process"""
    
    def __init__(self):
        # Validate required environment variables
        self.do_token = os.getenv("DO_TOKEN")
        if not self.do_token:
            raise ValueError("DO_TOKEN environment variable is required")
            
        self.project_id = os.getenv("DO_PROJECT_ID")
        self.project_name = os.getenv("PROJECT_NAME", "dvmdash-prod")
        self.betterstack_token = os.getenv("BETTERSTACK_TOKEN")
        if not self.betterstack_token:
            raise ValueError("BETTERSTACK_TOKEN environment variable is required")
            
        # Initialize managers
        self.postgres = PostgresManager(self.do_token, self.project_name)
        self.redis = RedisManager(self.do_token, self.project_name)
        self.betterstack = BetterStackLogger(self.project_name)
        
        # Store configurations and components
        self.postgres_config = None
        self.redis_config = None
        self.event_collector = None
        self.batch_processor = None
        self.monthly_archiver = None
        self.api_service = None
        self.frontend_service = None
        
    async def stage1_provision_databases(self):
        """Stage 1: Provision and configure databases"""
        try:
            logger.info("Starting Stage 1: Database Provisioning")
            
            # Provision databases concurrently
            self.postgres_config, self.redis_config = await asyncio.gather(
                self.postgres.provision(self.project_id),
                self.redis.provision(self.project_id)
            )
            
            # Wait for user confirmation
            details = {
                "PostgreSQL": f"Host: {self.postgres_config['host']}, Port: {self.postgres_config['port']}",
                "Redis": f"Host: {self.redis_config['host']}, Port: {self.redis_config['port']}"
            }
            
            continue_deploy, destroy = await confirm_stage("Stage 1: Database Provisioning", details)
            if continue_deploy:
                logger.info("Stage 1 completed successfully!")
                return True
            else:
                if destroy:
                    logger.warning("User requested infrastructure destruction after Stage 1")
                else:
                    logger.warning("User aborted deployment after Stage 1")
                await self.cleanup()
                return False
            
        except Exception as e:
            logger.error(f"Stage 1 failed: {str(e)}")
            await self.cleanup()
            return False
            
    async def stage2_deploy_backend_services(self) -> bool:
        """Stage 2: Deploy backend services"""
        try:
            logger.info("Starting Stage 2: Backend Services Deployment")
            
            # Create log sources with proper error handling
            ec_logs_token = self.betterstack.create_source("event-collector")
            if not ec_logs_token:
                raise ValueError("Failed to create event-collector log source")
                
            bp_logs_token = self.betterstack.create_source("batch-processor")
            if not bp_logs_token:
                raise ValueError("Failed to create batch-processor log source")
                
            ma_logs_token = self.betterstack.create_source("monthly-archiver")
            if not ma_logs_token:
                raise ValueError("Failed to create monthly-archiver log source")
            
            logger.info("Successfully created all log sources")
            
            # Initialize service managers
            self.event_collector = EventCollector(
                self.do_token,
                self.project_name,
                self.redis_config
            )
            
            self.batch_processor = BatchProcessor(
                self.do_token,
                self.project_name,
                self.redis_config,
                self.postgres_config
            )
            
            self.monthly_archiver = MonthlyArchiver(
                self.do_token,
                self.project_name,
                self.redis_config,
                self.postgres_config
            )
            
            # Deploy monthly archiver first
            logger.info("Deploying monthly archiver...")
            await self.monthly_archiver.deploy(
                branch="main",
                logs_token=ma_logs_token,
                project_id=self.project_id
            )
            
            # Deploy first batch processor
            logger.info("Deploying initial batch processor...")
            await self.batch_processor.deploy(
                branch="main",
                logs_token=bp_logs_token,
                project_id=self.project_id
            )
            
            # Deploy event collector
            logger.info("Deploying event collector...")
            await self.event_collector.deploy(
                branch="main",
                logs_token=ec_logs_token,
                project_id=self.project_id
            )
            
            # Scale remaining batch processors after event collector is running
            if NUM_BATCH_PROCESSORS > 1:
                logger.info(f"Scaling batch processors to {NUM_BATCH_PROCESSORS} instances...")
                await self.batch_processor.scale(NUM_BATCH_PROCESSORS)
            
            # Wait for user confirmation
            details = {
                "Event Collector": "Deployed and running",
                "Batch Processor": f"Deployed and scaled to {NUM_BATCH_PROCESSORS} instances",
                "Monthly Archiver": "Deployed and running"
            }
            
            continue_deploy, destroy = await confirm_stage("Stage 2: Backend Services Deployment", details)
            if continue_deploy:
                logger.info("Stage 2 completed successfully!")
                return True
            else:
                if destroy:
                    logger.warning("User requested infrastructure destruction after Stage 2")
                else:
                    logger.warning("User aborted deployment after Stage 2")
                await self.cleanup_stage2()
                await self.cleanup()
                return False
            
        except Exception as e:
            logger.error(f"Stage 2 failed: {str(e)}")
            await self.cleanup_stage2()
            return False
            
    async def cleanup_stage2(self):
        """Clean up Stage 2 resources"""
        cleanup_tasks = []
        
        if self.event_collector:
            cleanup_tasks.append(self.event_collector.cleanup())
        if self.batch_processor:
            cleanup_tasks.append(self.batch_processor.cleanup())
        if self.monthly_archiver:
            cleanup_tasks.append(self.monthly_archiver.cleanup())
            
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks)
            
    async def stage3_deploy_frontend_and_finalize(self) -> bool:
        """Stage 3: Deploy API and frontend, finalize event collector"""
        try:
            logger.info("Starting Stage 3: Frontend Deployment and Finalization")
            
            # Create log sources with proper error handling
            api_logs_token = self.betterstack.create_source("api")
            if not api_logs_token:
                raise ValueError("Failed to create api log source")
                
            frontend_logs_token = self.betterstack.create_source("frontend")
            if not frontend_logs_token:
                raise ValueError("Failed to create frontend log source")
                
            logger.info("Successfully created frontend/api log sources")
            
            # Initialize service managers
            self.api_service = ApiService(
                self.do_token,
                self.project_name,
                self.postgres_config
            )
            
            self.frontend_service = FrontendService(
                self.do_token,
                self.project_name
            )
            
            # Deploy API and frontend concurrently with explicit log tokens
            logger.info("Deploying API and frontend services...")
            await asyncio.gather(
                self.api_service.deploy(
                    branch="main",
                    logs_token=api_logs_token,
                    project_id=self.project_id
                ),
                self.frontend_service.deploy(
                    branch="main",
                    logs_token=frontend_logs_token,
                    project_id=self.project_id
                )
            )
            
            # Update event collector configuration and scale down
            logger.info("Updating event collector configuration and scaling down...")
            
            # Get current app spec
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.event_collector.app_id}",
                headers=self.event_collector.headers,
            )
            response.raise_for_status()
            current_spec = response.json()["app"]["spec"]
            
            # Update instance size and environment variables
            for component in current_spec["workers"]:
                if component["name"] == "worker":
                    component["instance_size_slug"] = "db-s-1vcpu-1gb"
                    for env in component["envs"]:
                        if env["key"] in {
                            "USE_TEST_DATA": "false",
                            "START_LISTENING": "true",
                            "RELAYS": "wss://relay.damus.io,wss://relay.primal.net,wss://relay.dvmdash.live,wss://relay.f7z.xyz,wss://relayable.org"
                        }:
                            env["value"] = {
                                "USE_TEST_DATA": "false",
                                "START_LISTENING": "true",
                                "RELAYS": "wss://relay.damus.io,wss://relay.primal.net,wss://relay.dvmdash.live,wss://relay.f7z.xyz,wss://relayable.org"
                            }[env["key"]]
                    break
            
            # Update the app
            response = requests.put(
                f"https://api.digitalocean.com/v2/apps/{self.event_collector.app_id}",
                headers=self.event_collector.headers,
                json={"spec": current_spec},
            )
            response.raise_for_status()
            
            # Wait for update to complete
            await self.event_collector.wait_for_app_ready()
            
            # Wait for user confirmation
            details = {
                "API Service": "Deployed and running",
                "Frontend Service": "Deployed and running",
                "Event Collector": "Configuration updated with production settings"
            }
            
            continue_deploy, destroy = await confirm_stage("Stage 3: Frontend Deployment and Finalization", details)
            if continue_deploy:
                logger.info("Stage 3 completed successfully!")
                return True
            else:
                if destroy:
                    logger.warning("User requested infrastructure destruction after Stage 3")
                else:
                    logger.warning("User aborted deployment after Stage 3")
                await self.cleanup_stage3()
                await self.cleanup_stage2()
                await self.cleanup()
                return False
            
        except Exception as e:
            logger.error(f"Stage 3 failed: {str(e)}")
            await self.cleanup_stage3()
            return False
            
    async def cleanup_stage3(self):
        """Clean up Stage 3 resources"""
        cleanup_tasks = []
        
        if self.api_service:
            cleanup_tasks.append(self.api_service.cleanup())
        if self.frontend_service:
            cleanup_tasks.append(self.frontend_service.cleanup())
            
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks)
            
    async def cleanup(self):
        """Clean up all resources on failure"""
        logger.info("Cleaning up resources...")
        cleanup_tasks = [
            self.postgres.cleanup(),
            self.redis.cleanup(),
        ]
        
        if self.event_collector:
            cleanup_tasks.append(self.event_collector.cleanup())
        if self.batch_processor:
            cleanup_tasks.append(self.batch_processor.cleanup())
        if self.monthly_archiver:
            cleanup_tasks.append(self.monthly_archiver.cleanup())
        if self.api_service:
            cleanup_tasks.append(self.api_service.cleanup())
        if self.frontend_service:
            cleanup_tasks.append(self.frontend_service.cleanup())
            
        await asyncio.gather(*cleanup_tasks)
        
        if hasattr(self, 'betterstack'):
            self.betterstack.delete_sources()

async def main():
    """Main deployment function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Deploy DVM Dashboard production environment')
    parser.add_argument('--stage', type=int, choices=[1, 2, 3], help='Start deployment from a specific stage (1-3)')
    args = parser.parse_args()
    
    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
        
    deployment = DeploymentManager()
    try:
        start_stage = args.stage if args.stage else 1
        logger.info(f"Starting deployment from stage {start_stage}")
        
        # Stage 1: Database Provisioning
        if start_stage <= 1:
            if not await deployment.stage1_provision_databases():
                logger.error("Deployment failed at Stage 1")
                sys.exit(1)
        else:
            logger.info("Skipping Stage 1 (Database Provisioning)")
            
        # Stage 2: Backend Services
        if start_stage <= 2:
            if not await deployment.stage2_deploy_backend_services():
                logger.error("Deployment failed at Stage 2")
                sys.exit(1)
        else:
            logger.info("Skipping Stage 2 (Backend Services)")
            
        # Stage 3: Frontend and Finalization
        if start_stage <= 3:
            if not await deployment.stage3_deploy_frontend_and_finalize():
                logger.error("Deployment failed at Stage 3")
                sys.exit(1)
            
        logger.info("Deployment completed successfully!")
        
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}")
        await deployment.cleanup()
        sys.exit(1)
        
async def shutdown(sig):
    """Handle shutdown gracefully"""
    logger.info(f"Received exit signal {sig.name}...")
    shutdown_event.set()

if __name__ == "__main__":
    asyncio.run(main())
