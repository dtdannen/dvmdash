import asyncio
import os
import signal
from typing import Optional
import requests
from loguru import logger
from dotenv import load_dotenv

# Import your existing infrastructure classes
from production_components import (
    PostgresTestRunner,
    RedisRunner,
    EventCollectorAppPlatformRunner,
    BatchProcessorAppPlatformRunner,
    MonthlyArchiverAppPlatformRunner,
    BetterStackLogsRunner,
)

PROJECT_NAME = "dvmdash_production"


class APIAppPlatformRunner:
    """Sets up the App Platform for the API service"""

    def __init__(self, do_token: str, project_name: str, postgres_config, redis_config):
        self.token = do_token
        self.project_name = project_name
        self.name_prefix = "api"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.app_id = None
        self.postgres_config = postgres_config
        self.redis_config = redis_config

    async def setup_app_platform(
        self, branch: str = "main", betterstack_rsyslog_token: Optional[str] = None
    ):
        logger.info(f"Creating {self.project_name}-{self.name_prefix} API service...")
        # Implementation similar to your other app platform runners
        # Configure with appropriate env vars, ports, etc.
        pass

    async def cleanup_app_platform(self):
        # Cleanup implementation
        pass


class FrontendAppPlatformRunner:
    """Sets up the App Platform for the Next.js frontend"""

    def __init__(self, do_token: str, project_name: str, api_url: str):
        self.token = do_token
        self.project_name = project_name
        self.name_prefix = "frontend"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.app_id = None
        self.api_url = api_url

    async def setup_app_platform(
        self, branch: str = "main", betterstack_rsyslog_token: Optional[str] = None
    ):
        logger.info(
            f"Creating {self.project_name}-{self.name_prefix} frontend service..."
        )
        # Implementation for deploying Next.js app
        pass

    async def cleanup_app_platform(self):
        # Cleanup implementation
        pass


async def stage_one_deployment(project_name: str, do_token: str):
    """Stage 1: Set up infrastructure and load historical data"""
    logger.info(
        "Starting Stage 1 deployment - Infrastructure setup and historical data load"
    )

    # Initialize infrastructure managers
    betterstack = BetterStackLogsRunner(project_name)
    postgres_db = PostgresTestRunner(do_token, project_name, "pipeline")
    redis_db = RedisRunner(do_token, project_name)

    try:
        # Set up databases
        await asyncio.gather(
            postgres_db.setup_database(os.getenv("DO_PROJECT_ID")),
            redis_db.setup_database(os.getenv("DO_PROJECT_ID")),
        )

        # Deploy services for historical data processing
        event_collector = EventCollectorAppPlatformRunner(
            do_token, project_name, redis_db.db_config
        )

        batch_processor = BatchProcessorAppPlatformRunner(
            do_token, project_name, redis_db.db_config, postgres_db.db_config
        )

        monthly_archiver = MonthlyArchiverAppPlatformRunner(
            do_token, project_name, redis_db.db_config, postgres_db.db_config
        )

        # Deploy services with historical data loading configuration
        await asyncio.gather(
            event_collector.setup_app_platform(
                branch="main",
                betterstack_rsyslog_token=betterstack.create_source("event-collector"),
                env_overrides={"USE_TEST_DATA": "true"},
            ),
            batch_processor.setup_app_platform(
                branch="main",
                betterstack_rsyslog_token=betterstack.create_source("batch-processor"),
            ),
            monthly_archiver.setup_app_platform(
                branch="main",
                betterstack_rsyslog_token=betterstack.create_source("monthly-archiver"),
            ),
        )

        # Monitor progress until historical data is loaded
        while not shutdown_event.is_set():
            # Monitor Redis queue and PostgreSQL state
            # Return when historical data loading is complete
            await asyncio.sleep(10)

        return {
            "postgres_db": postgres_db,
            "redis_db": redis_db,
            "event_collector": event_collector,
            "batch_processor": batch_processor,
            "monthly_archiver": monthly_archiver,
            "betterstack": betterstack,
        }

    except Exception as e:
        logger.error(f"Stage 1 deployment failed: {e}")
        raise


async def stage_two_deployment(infrastructure, project_name: str, do_token: str):
    """Stage 2: Deploy production services"""
    logger.info("Starting Stage 2 deployment - Production services")

    try:
        # Reconfigure event collector for live data
        await infrastructure["event_collector"].update_configuration(
            env_updates={"USE_TEST_DATA": "false"}
        )

        # Deploy API service
        api_service = APIAppPlatformRunner(
            do_token,
            project_name,
            infrastructure["postgres_db"].db_config,
            infrastructure["redis_db"].db_config,
        )

        await api_service.setup_app_platform(
            branch="main",
            betterstack_rsyslog_token=infrastructure["betterstack"].create_source(
                "api"
            ),
        )

        # Get API URL for frontend configuration
        api_url = await api_service.get_service_url()

        # Deploy frontend
        frontend = FrontendAppPlatformRunner(do_token, project_name, api_url)
        await frontend.setup_app_platform(
            branch="main",
            betterstack_rsyslog_token=infrastructure["betterstack"].create_source(
                "frontend"
            ),
        )

        return {**infrastructure, "api_service": api_service, "frontend": frontend}

    except Exception as e:
        logger.error(f"Stage 2 deployment failed: {e}")
        raise


async def cleanup_deployment(services):
    """Clean up all deployed services and infrastructure"""
    cleanup_tasks = []
    for service in services.values():
        if hasattr(service, "cleanup_app_platform"):
            cleanup_tasks.append(service.cleanup_app_platform())
        elif hasattr(service, "cleanup"):
            cleanup_tasks.append(service.cleanup())

    if cleanup_tasks:
        await asyncio.gather(*cleanup_tasks)
    logger.info("Deployment cleanup completed")


async def main():
    load_dotenv()
    do_token = os.getenv("DO_TOKEN")
    if not do_token:
        raise ValueError("DO_TOKEN environment variable is required")

    project_name = "your-production-project-name"

    try:
        # Stage 1: Infrastructure and historical data
        print(f"Starting stage one of deployment for project: {project_name}")
        stage_one_infra = await stage_one_deployment(project_name, do_token)

        print(f"Starting stage two of deployment for project: {project_name}")

        # Stage 2: Production services
        all_services = await stage_two_deployment(
            stage_one_infra, project_name, do_token
        )

    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
