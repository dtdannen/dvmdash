import asyncio
import json
import random

import requests
import asyncpg
from datetime import datetime
import os
from typing import Dict, Optional
import redis.asyncio as redis
from loguru import logger
from dotenv import load_dotenv
import time
from asyncio import Queue
import matplotlib.pyplot as plt
import numpy as np
import signal

# handle signal to shutdown so we shutdown gracefully
shutdown_event = asyncio.Event()
metrics_queue = Queue()

load_dotenv()


class MetricsCollector:
    """Collects and stores metrics from various components"""

    def __init__(self, redis_client):
        self.metrics_history = []
        self.redis_db_info = redis_client

    async def monitor_redis_items(self, redis_client, delay: int = 1):
        while not shutdown_event.is_set():
            try:
                # Only get dvmdash_events count
                events_count = await redis_client.llen("dvmdash_events")
                processed_count = await redis_client.scard("dvmdash_processed_events")

                # Get memory info
                memory_info = await redis_client.info("memory")
                used_memory_mb = int(memory_info["used_memory"]) / (1024 * 1024)

                print(
                    f"Events: {events_count}, Processed: {processed_count}, Memory: {used_memory_mb:.2f}MB"
                )
                await asyncio.sleep(delay)
            except redis.RedisError as e:
                logger.error(f"Redis error: {e}")
                await asyncio.sleep(delay)

    async def collect_metrics(
        self,
        postgres_runners: Dict[str, "PostgresTestRunner"],
        redis_client: Optional[redis.Redis] = None,
    ):
        """Collect metrics from all components every second"""
        while not shutdown_event.is_set():
            metrics = {}

            # Collect Postgres metrics
            for db_name, runner in postgres_runners.items():
                if runner.pool:
                    async with runner.pool.acquire() as conn:
                        count = await conn.fetchval("SELECT COUNT(*) FROM raw_events")
                        metrics[f"{db_name}_event_count"] = count

            # Collect Redis metrics if available
            if redis_client:
                # TODO: Implement Redis metrics collection
                # - List length for pending events
                # - Memory usage
                # - Processed events count
                pass

            # Add timestamp
            metrics["timestamp"] = datetime.now().isoformat()

            # Store metrics
            self.metrics_history.append(metrics)
            await metrics_queue.put(metrics)

            await asyncio.sleep(1)


class BetterStackLogsRunner:
    """Create betterstack logs so we can get all logs from the app platform"""

    def __init__(self, project_name: str):
        self.project_name = project_name

    def create_source(self, service_name: str):
        BETTERSTACK_TOKEN = os.getenv("BETTERSTACK_TOKEN")

        url = "https://telemetry.betterstack.com/api/v1/sources"

        headers = {"Authorization": f"Bearer {BETTERSTACK_TOKEN}"}

        payload = {
            "name": f"{self.project_name}-{service_name}",
            "platform": "rsyslog",
        }

        # send the request
        response = requests.post(url, headers=headers, json=payload)

        # check if the request was successful
        print(response.json())
        if response.status_code == 201:
            print("Source created successfully")
            response_json = response.json()
            if "data" in response_json:
                if "attributes" in response_json["data"]:
                    if "token" in response_json["data"]["attributes"]:
                        print(
                            "logs token is: "
                            + response_json["data"]["attributes"]["token"]
                        )
                        return response_json["data"]["attributes"]["token"]
                    else:
                        print(f"No token in response['attributes']")
                else:
                    print(f"No attributes in response['data']")
            else:
                print(f"No data in response")

        else:
            print("Error creating source")
            print(response.text)


class EventCollectorAppPlatformRunner:
    """Sets up the App Platform for both the event collector and batch processor on Digital Ocean"""

    def __init__(self, do_token: str, project_name: str, redis_db_config):
        self.token = do_token
        self.project_name = project_name
        self.name_prefix = "event_collector"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.app_id = None
        self.redis_db_config = redis_db_config

    async def setup_app_platform(
        self, branch: str = "main", betterstack_rsyslog_token: str = None
    ):
        logger.info("Creating App Platform application...")

        event_collector_app_spec = {
            "spec": {
                "name": f"{self.project_name}-event-collector",  # Changed underscore to hyphen
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
                        "dockerfile_path": "backend/event_collector/Dockerfile",
                        "log_destinations": [
                            {
                                "name": "betterstack",
                                "logtail": {
                                    "token": betterstack_rsyslog_token,
                                },
                            }
                        ],
                        "envs": [
                            {
                                "key": "REDIS_URL",
                                "value": f"rediss://default:{self.redis_db_config['password']}@"
                                f"{self.redis_db_config['host']}:{self.redis_db_config['port']}",
                                "type": "SECRET",
                            },
                        ],
                    }
                ],
            },
            "project_id": os.getenv("DO_PROJECT_ID"),
        }

        print(
            f"About to send spec to do for event collector: {json.dumps(event_collector_app_spec, indent=2)}"
        )

        response = requests.post(
            "https://api.digitalocean.com/v2/apps",
            headers=self.headers,
            json=event_collector_app_spec,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            print(f"Error response: {response.text}")
            raise

        self.app_id = response.json()["app"]["id"]

        logger.info("Waiting for App Platform application to be ready...")
        while True:
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            ).json()

            # Print response to debug
            # print(f"Status response: {json.dumps(response, indent=2)}")

            # Change this line to match actual response structure
            app_content = response.get("app")
            print(f"App content: {app_content}")
            if app_content:
                active_deployment = app_content.get("active_deployment")
                print(f"Active deployment: {active_deployment}")
                if active_deployment:
                    phase = active_deployment.get("phase")
                    print(f"Phase: {phase}")
                    if phase == "ACTIVE":
                        print(f"App is active")
                        break

            await asyncio.sleep(10)

        logger.info("App Platform application is ready!")

    async def cleanup_app_platform(self):
        if self.app_id:
            logger.info("Cleaning up App Platform application...")
            response = requests.delete(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            logger.info("App Platform application cleaned up successfully")


class PostgresTestRunner:
    """Existing PostgresTestRunner with minimal modifications"""

    def __init__(self, do_token: str, project_name: str, name_prefix: str = "events"):
        self.token = do_token
        self.project_name = project_name
        self.db_id = None
        self.db_config = None
        self.pool = None
        self.name_prefix = name_prefix

    async def _init_db_pool(self):
        self.pool = await asyncpg.create_pool(**self.db_config)

    async def setup_database(self, project_id: str = None) -> None:
        """Create and configure DO managed Postgres database"""
        logger.info(f"Creating managed Postgres database ({self.name_prefix})...")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        create_params = {
            "name": f"{self.project_name}-{self.name_prefix}",
            "engine": "pg",
            "version": "16",
            "size": "db-s-1vcpu-1gb",
            "region": "nyc1",
            "num_nodes": 1,
        }

        if project_id:
            create_params["project_id"] = project_id

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
            status = requests.get(
                f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                headers=headers,
            ).json()["database"]["status"]
            if status == "online":
                break
            await asyncio.sleep(10)

        # Get connection details
        db_info = requests.get(
            f"https://api.digitalocean.com/v2/databases/{self.db_id}", headers=headers
        ).json()["database"]

        self.db_config = {
            "host": db_info["connection"]["host"],
            "port": db_info["connection"]["port"],
            "database": "defaultdb",
            "user": db_info["connection"]["user"],
            "password": db_info["connection"]["password"],
        }

        await self._init_db_pool()

        # Initialize schema
        if self.name_prefix == "events":
            logger.info("Initializing EVENTS database schema...")
            with open("infrastructure/postgres/events_init.sql", "r") as f:
                schema = f.read()
        elif self.name_prefix == "pipeline":
            logger.info("Initializing PIPELINE database schema...")
            with open("infrastructure/postgres/pipeline_init.sql", "r") as f:
                schema = f.read()

        async with self.pool.acquire() as conn:
            await conn.execute(schema)

        logger.info("Database setup complete!")

    async def cleanup(self) -> None:
        """Clean up resources"""
        if self.pool:
            await self.pool.close()

        if self.db_id:
            logger.info("Cleaning up database...")
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            response = requests.delete(
                f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                headers=headers,
            )
            response.raise_for_status()
            logger.info("Database cleaned up successfully")


class RedisRunner:
    """Manages a Redis managed database on Digital Ocean"""

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
            ssl=True,  # DO managed Redis requires SSL
            decode_responses=True,  # For convenience in handling strings
        )
        # Test the connection
        await self.redis_client.ping()

    async def setup_database(self, project_id: str = None) -> None:
        """Create and configure DO managed Redis database"""
        logger.info("Creating managed Redis database...")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        create_params = {
            "name": f"{self.project_name}-redis",
            "engine": "redis",
            "version": "7",
            "size": "db-s-1vcpu-1gb",
            "region": "nyc1",
            "num_nodes": 1,
        }

        if project_id:
            create_params["project_id"] = project_id

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
            status = requests.get(
                f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                headers=headers,
            ).json()["database"]["status"]
            if status == "online":
                break
            await asyncio.sleep(10)

        # Get connection details
        db_info = requests.get(
            f"https://api.digitalocean.com/v2/databases/{self.db_id}", headers=headers
        ).json()["database"]

        self.db_config = {
            "host": db_info["connection"]["host"],
            "port": db_info["connection"]["port"],
            "password": db_info["connection"]["password"],
        }

        await self._init_redis_client()
        logger.info("Redis database setup complete!")

    async def cleanup(self) -> None:
        """Clean up Redis managed database"""
        if self.redis_client:
            await self.redis_client.close()

        if self.db_id:
            logger.info("Cleaning up Redis database...")
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            response = requests.delete(
                f"https://api.digitalocean.com/v2/databases/{self.db_id}",
                headers=headers,
            )
            response.raise_for_status()
            logger.info("Redis database cleaned up successfully")


async def setup_infrastructure(
    do_token: str, project_name: str, project_id: str = None
):
    """Setup all required infrastructure components"""
    # Initialize runners
    events_db = PostgresTestRunner(do_token, project_name, "events")
    metrics_db = PostgresTestRunner(do_token, project_name, "pipeline")
    redis_runner = RedisRunner(do_token, project_name)

    # Setup components
    await asyncio.gather(
        events_db.setup_database(project_id),
        metrics_db.setup_database(project_id),
        redis_runner.setup_database(project_id),
    )

    return events_db, metrics_db, redis_runner


async def shutdown(runner):
    """Graceful shutdown"""
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_event.set()


async def main():
    do_token = os.getenv("DO_TOKEN")
    if not do_token:
        raise ValueError("DO_TOKEN environment variable is required")

    # create a name on demand for this project so all services can be associated together easily
    random_color_word = random.choice(
        [
            "red",
            "blue",
            "green",
            "yellow",
            "purple",
            "orange",
            "pink",
            "brown",
            "black",
            "white",
            "gray",
        ]
    )

    random_animal_word = random.choice(
        [
            "dog",
            "cat",
            "bird",
            "fish",
            "rabbit",
            "mouse",
            "horse",
            "cow",
            "sheep",
            "pig",
            "chicken",
            "duck",
            "goat",
            "turkey",
        ]
    )

    project_name = f"{random_color_word}-{random_animal_word}"
    print(f"PROJECT_NAME={project_name}")
    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    events_db, metrics_db, redis_runner = None, None, None
    try:
        # create a better stack logs runner
        betterstack_log_runner = BetterStackLogsRunner(project_name)
        print(f"Created betterstack runner with project name is {project_name}")

        # Setup managed databases
        events_db, metrics_db, redis_runner = await setup_infrastructure(
            do_token, project_name, project_id=os.getenv("DO_PROJECT_ID")
        )

        print(f"Redis db config is {redis_runner.db_config}")
        # Setup App Platform
        logs_token = betterstack_log_runner.create_source("event-collector")
        print(f"Logs token: {logs_token}")
        app_runner = EventCollectorAppPlatformRunner(
            do_token, project_name=project_name, redis_db_config=redis_runner.db_config
        )
        await app_runner.setup_app_platform(
            branch="full-redesign", betterstack_rsyslog_token=logs_token
        )
        print(f"App runner setup for event collector complete")

        # todo - test the following code after this line, everything before is working
        # Initialize metrics collector
        metrics_collector = MetricsCollector(redis_runner.redis_client)

        tasks = [metrics_collector.monitor_redis_items(redis_runner.redis_client)]
        running_tasks = [asyncio.create_task(t) for t in tasks]

        done, pending = await asyncio.wait(
            running_tasks, return_when=asyncio.FIRST_EXCEPTION
        )

        # Handle any exceptions
        for task in done:
            try:
                await task
            except Exception as e:
                logger.error(f"Task failed: {e}")

    finally:
        # Cancel pending tasks
        if running_tasks:
            for task in running_tasks:
                task.cancel()
            await asyncio.gather(*running_tasks, return_exceptions=True)
        # Cleanup
        await asyncio.gather(
            events_db.cleanup(),
            metrics_db.cleanup(),
            redis_runner.cleanup(),
            app_runner.cleanup_app_platform(),
        )


if __name__ == "__main__":
    asyncio.run(main())
