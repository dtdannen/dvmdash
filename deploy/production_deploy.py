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
    
    def __init__(self, postgres_config: Optional[Dict] = None):
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
        if postgres_config:
            self.postgres_config = postgres_config
            self.postgres = None  # Don't initialize PostgresManager if config provided
        else:
            self.postgres = PostgresManager(self.do_token, self.project_name)
            self.postgres_config = None
            
        self.redis = RedisManager(self.do_token, self.project_name)
        self.betterstack = BetterStackLogger(self.project_name)
        
        # Store configurations and components
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
            if self.postgres:
                self.postgres_config, self.redis_config = await asyncio.gather(
                    self.postgres.provision(self.project_id),
                    self.redis.provision(self.project_id)
                )
            else:
                self.redis_config = await self.redis.provision(self.project_id)
            
            # Wait for user confirmation
            details = {
                "PostgreSQL": f"Host: {self.postgres_config['host']}, Port: {self.postgres_config['port']}" if self.postgres_config else "Using existing database",
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
            
    async def stage3_deploy_frontend(self) -> bool:
        """Stage 4: Deploy frontend service"""
        try:
            logger.info("Starting Stage 4: Frontend Service Deployment")
            
            # Create log source with proper error handling
            frontend_logs_token = self.betterstack.create_source("frontend")
            if not frontend_logs_token:
                raise ValueError("Failed to create frontend log source")
                
            logger.info("Successfully created frontend log source")
            
            # Initialize frontend service manager
            self.frontend_service = FrontendService(
                self.do_token,
                self.project_name
            )
            
            # Deploy frontend service
            logger.info("Deploying frontend service...")
            try:
                await self.frontend_service.deploy(
                    branch="main",
                    logs_token=frontend_logs_token,
                    project_id=self.project_id
                )
            except Exception as deploy_error:
                logger.error(f"Frontend deployment failed: {str(deploy_error)}")
                logger.info("Skipping cleanup to allow inspection of build errors in DigitalOcean console")
                return False
            
            # Wait for user confirmation
            details = {
                "Frontend Service": "Deployed and running"
            }
            
            continue_deploy, destroy = await confirm_stage("Stage 3: Frontend Service Deployment", details)
            if continue_deploy:
                logger.info("Stage 3 completed successfully!")
                return True
            else:
                if destroy:
                    logger.warning("User requested infrastructure destruction after Stage 3")
                    await self.cleanup_stage3()
                    await self.cleanup_stage2()
                    await self.cleanup()
                else:
                    logger.warning("User aborted deployment after Stage 3")
                return False
            
        except Exception as e:
            logger.error(f"Stage 3 failed: {str(e)}")
            return False
            
    async def cleanup_stage3(self):
        """Clean up Stage 3 resources"""
        if self.frontend_service:
            await self.frontend_service.cleanup()

    async def stage4_deploy_api(self) -> bool:
        """Stage 4: Deploy API service"""
        try:
            logger.info("Starting Stage 4: API Service Deployment")
            
            # Create log source with proper error handling
            api_logs_token = self.betterstack.create_source("api")
            if not api_logs_token:
                raise ValueError("Failed to create api log source")
                
            logger.info("Successfully created api log source")
            
            # Get frontend URL
            frontend_url = None
            if self.frontend_service:
                try:
                    frontend_url = await self.frontend_service.get_app_url()
                    logger.info(f"Using frontend URL: {frontend_url}")
                except Exception as e:
                    logger.warning(f"Failed to get frontend URL: {str(e)}")
            
            # Initialize API service manager
            self.api_service = ApiService(
                self.do_token,
                self.project_name,
                self.postgres_config
            )
            
            # Deploy API service
            logger.info("Deploying API service...")
            await self.api_service.deploy(
                branch="main",
                logs_token=api_logs_token,
                project_id=self.project_id,
                frontend_url=frontend_url
            )
            
            # Wait for user confirmation
            details = {
                "API Service": "Deployed and running",
                "CORS Configuration": f"Using frontend URL: {frontend_url or '${APP_DOMAIN}'}"
            }
            
            continue_deploy, destroy = await confirm_stage("Stage 4: API Service Deployment", details)
            if continue_deploy:
                logger.info("Stage 4 completed successfully!")
                return True
            else:
                if destroy:
                    logger.warning("User requested infrastructure destruction after Stage 4")
                    await self.cleanup_stage4()
                    await self.cleanup_stage3()
                    await self.cleanup_stage2()
                    await self.cleanup()
                else:
                    logger.warning("User aborted deployment after Stage 4")
                return False
            
        except Exception as e:
            logger.error(f"Stage 4 failed: {str(e)}")
            await self.cleanup_stage4()
            return False
            
    async def cleanup_stage4(self):
        """Clean up Stage 4 resources"""
        if self.api_service:
            await self.api_service.cleanup()
            
    async def cleanup(self):
        """Clean up all resources on failure"""
        logger.info("Cleaning up resources...")
        cleanup_tasks = [self.redis.cleanup()]
        
        if self.postgres:
            cleanup_tasks.append(self.postgres.cleanup())
        
        if self.event_collector:
            cleanup_tasks.append(self.event_collector.cleanup())
        if self.batch_processor:
            cleanup_tasks.append(self.batch_processor.cleanup())
        if self.monthly_archiver:
            cleanup_tasks.append(self.monthly_archiver.cleanup())
        if self.api_service:
            cleanup_tasks.append(self.api_service.cleanup())
        #if self.frontend_service:
        #    cleanup_tasks.append(self.frontend_service.cleanup())
            
        await asyncio.gather(*cleanup_tasks)
        
        if hasattr(self, 'betterstack'):
            self.betterstack.delete_sources()

async def main():
    """Main deployment function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Deploy DVM Dashboard production environment')
    parser.add_argument('--stage', type=int, choices=[1, 2, 3, 4], help='Start deployment from a specific stage (1-4)')
    
    # Add PostgreSQL configuration arguments
    parser.add_argument('--postgres-host', help='PostgreSQL host (required for stage 3)')
    parser.add_argument('--postgres-port', type=int, help='PostgreSQL port (required for stage 3)')
    parser.add_argument('--postgres-db', help='PostgreSQL database name (required for stage 3)')
    parser.add_argument('--postgres-user', help='PostgreSQL user (required for stage 3)')
    parser.add_argument('--postgres-password', help='PostgreSQL password (required for stage 3)')
    
    args = parser.parse_args()
    
    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
    
    # Validate PostgreSQL configuration if starting at stage 3
    postgres_config = None
    if args.stage == 3:
        required_postgres_args = [
            ('postgres_host', 'PostgreSQL host'),
            ('postgres_port', 'PostgreSQL port'),
            ('postgres_db', 'PostgreSQL database'),
            ('postgres_user', 'PostgreSQL user'),
            ('postgres_password', 'PostgreSQL password')
        ]
        
        missing_args = [desc for arg, desc in required_postgres_args if not getattr(args, arg.replace('-', '_'))]
        if missing_args:
            parser.error(f"The following arguments are required when starting at stage 3: {', '.join(missing_args)}")
            
        postgres_config = {
            "host": args.postgres_host,
            "port": args.postgres_port,
            "database": args.postgres_db,
            "user": args.postgres_user,
            "password": args.postgres_password
        }
        
    deployment = DeploymentManager(postgres_config)
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
            
        # Stage 3: Frontend Service
        if start_stage <= 3:
            try:
                if not await deployment.stage3_deploy_frontend():
                    logger.error("Deployment failed at Stage 3")
                    sys.exit(1)
            except Exception as e:
                logger.error("Stage 3 failed with detailed error:")
                if hasattr(e, "response") and e.response is not None:
                    try:
                        error_detail = e.response.json()
                        logger.error(f"API Response: {error_detail}")
                        if "error" in error_detail:
                            logger.error(f"Error message: {error_detail['error'].get('message', '')}")
                            logger.error(f"Error code: {error_detail['error'].get('code', '')}")
                    except:
                        logger.error(f"Raw response: {e.response.text}")
                else:
                    logger.error(str(e))
                sys.exit(1)
                
        # Stage 4: API Service
        if start_stage <= 4:
            try:
                if not await deployment.stage4_deploy_api():
                    logger.error("Deployment failed at Stage 4")
                    sys.exit(1)
            except Exception as e:
                logger.error("Stage 4 failed with detailed error:")
                if hasattr(e, "response") and e.response is not None:
                    try:
                        error_detail = e.response.json()
                        logger.error(f"API Response: {error_detail}")
                        if "error" in error_detail:
                            logger.error(f"Error message: {error_detail['error'].get('message', '')}")
                            logger.error(f"Error code: {error_detail['error'].get('code', '')}")
                    except:
                        logger.error(f"Raw response: {e.response.text}")
                else:
                    logger.error(str(e))
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
