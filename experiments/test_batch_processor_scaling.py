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
import csv

# handle signal to shutdown so we shutdown gracefully
shutdown_event = asyncio.Event()
metrics_queue = Queue()

load_dotenv()


class MetricsCollector:
    """Collects and stores metrics from various components"""

    def __init__(self, redis_client, project_name: str, num_batch_processors: int):
        self.metrics_history = []
        self.redis_db_info = redis_client
        self.project_name = project_name
        self.start_time = None
        self.last_redis_count = 0
        self.last_postgres_count = 0
        self.collection_interval = 2  # seconds
        self.num_batch_processors = num_batch_processors

        # Create metrics directory if it doesn't exist
        self.metrics_dir = "experiments/data"
        if not os.path.exists(self.metrics_dir):
            os.makedirs(self.metrics_dir)

        # Create run-specific directory
        self.run_timestamp = datetime.now().strftime("%Y_%b_%d_at_%H_%M_%S")
        self.run_dir = os.path.join(self.metrics_dir, f"run_{self.run_timestamp}")
        os.makedirs(self.run_dir)
        logger.info(f"Created run directory: {self.run_dir}")

        self.csv_filename = f"{self.run_dir}/{self.project_name}_{self.num_batch_processors}BP_{self.run_timestamp}_metrics.csv"
        self.initialize_csv()
        logger.info(f"Initialized CSV file: {self.csv_filename}")

    def initialize_csv(self):
        """Initialize CSV file with updated headers"""
        with open(self.csv_filename, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "time_since_start",
                    "project",
                    "redis_queue_size",
                    "postgres_events",
                    "postgres_pipeline_entity_activity_count",
                ],
            )
            writer.writeheader()
        logger.debug("CSV file initialized with headers")

    async def monitor_redis_items(self, redis_client, delay: int = 1):
        while not shutdown_event.is_set():
            try:
                # Only get dvmdash_events count
                events_count = await redis_client.llen("dvmdash_events")
                processed_count = await redis_client.scard("dvmdash_processed_events")

                # Get memory info
                memory_info = await redis_client.info("memory")
                used_memory_mb = int(memory_info["used_memory"]) / (1024 * 1024)

                logger.info(
                    f"Events: {events_count}, Processed: {processed_count}, Memory: {used_memory_mb:.2f}MB"
                )
                await asyncio.sleep(delay)
            except redis.RedisError as e:
                logger.error(f"Redis error: {e}")
                await asyncio.sleep(delay)

    async def monitor_postgres_events_db(self, postgres_pool, delay: int = 1):
        while not shutdown_event.is_set():
            try:
                async with postgres_pool.acquire() as conn:
                    count = await conn.fetchval("SELECT COUNT(*) FROM raw_events")
                    logger.info(f"Events in Postgres: {count}")
                    await asyncio.sleep(delay)
            except asyncpg.exceptions.PostgresError as e:
                logger.error(f"Postgres error: {e}")
                await asyncio.sleep(delay)

    async def wait_for_queue_size(
        self,
        redis_client,
        target_size: int,
        check_interval: int = 10,
        timeout: int = 3600,
    ):
        """
        Wait for Redis queue to reach target size

        Args:
            redis_client: Redis client instance
            target_size: Target number of items in queue
            check_interval: How often to check queue size (seconds)
            timeout: Maximum time to wait (seconds)

        Returns:
            bool: True if target size reached, False if timeout occurred
        """
        start_time = time.time()
        logger.info(f"Waiting for Redis queue to reach {target_size:,} items...")

        while not shutdown_event.is_set():
            try:
                current_size = await redis_client.llen("dvmdash_events")
                processed_count = await redis_client.scard("dvmdash_processed_events")

                logger.info(
                    f"Current queue size: {current_size:,}, Processed: {processed_count:,}"
                )

                if current_size >= target_size:
                    logger.info(f"Target queue size of {target_size:,} reached!")
                    return True

                # Check timeout
                if time.time() - start_time > timeout:
                    logger.warning(f"Timeout reached after {timeout} seconds")
                    return False

                # Calculate and log ingestion rate
                await asyncio.sleep(check_interval)
                new_size = await redis_client.llen("dvmdash_events")
                rate = (new_size - current_size) / check_interval
                logger.info(f"Current ingestion rate: {rate:.2f} items/second")

                # Estimate time remaining
                if rate > 0:
                    items_remaining = target_size - new_size
                    time_remaining = items_remaining / rate
                    logger.info(
                        f"Estimated time remaining: {time_remaining:.2f} seconds"
                    )

            except redis.RedisError as e:
                logger.error(f"Redis error while monitoring queue size: {e}")
                await asyncio.sleep(check_interval)

        return False

    async def check_redis_empty(self, redis_client, delay: int = 5):
        """Monitor Redis queue and trigger shutdown when empty"""
        while not shutdown_event.is_set():
            try:
                # this check is to avoid premature shutdown
                if self.start_time is not None:
                    queue_size = await redis_client.llen("dvmdash_events")
                    if queue_size == 0:
                        logger.info("Redis queue is empty, initiating shutdown...")
                        shutdown_event.set()
                        return
                await asyncio.sleep(delay)
            except redis.RedisError as e:
                logger.error(f"Redis error while checking queue: {e}")
                await asyncio.sleep(delay)

    # Add this method for a more detailed progress visualization
    async def monitor_queue_progress(self, redis_client, target_size: int):
        """Monitor and display queue progress with percentage and progress bar"""
        try:
            current_size = await redis_client.llen("dvmdash_events")
            percentage = min(100, (current_size / target_size) * 100)
            bar_length = 50
            filled_length = int(bar_length * current_size / target_size)
            bar = "=" * filled_length + "-" * (bar_length - filled_length)

            logger.info(
                f"Progress: [{bar}] {percentage:.1f}% ({current_size:,}/{target_size:,})"
            )
        except redis.RedisError as e:
            logger.error(f"Error monitoring progress: {e}")

    async def collect_metrics_history(self, redis_client, postgres_pipeline_pool):
        """Collect and store metrics history with timestamps"""
        while not shutdown_event.is_set():
            try:
                # Skip collection if start time hasn't been set
                if self.start_time is None:
                    await asyncio.sleep(2)
                    continue

                time_since_start = time.time() - self.start_time

                metrics = {
                    "time_since_start": f"{time_since_start:.3f}",
                    "project": self.project_name,
                    "redis_queue_size": await redis_client.llen("dvmdash_events"),
                    "postgres_events": await postgres_pipeline_pool.fetchval(
                        "SELECT COUNT(*) FROM raw_events"
                    ),
                    "postgres_pipeline_entity_activity_count": await postgres_pipeline_pool.fetchval(
                        "SELECT COUNT(*) FROM entity_activity"
                    ),
                }

                self.metrics_history.append(metrics)

                # Write to CSV file
                with open(self.csv_filename, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=metrics.keys())
                    writer.writerow(metrics)

                # Log current metrics
                logger.info(
                    f"Metrics at {time_since_start:,.3f}s: "
                    f"Redis Queue={metrics['redis_queue_size']:,}, "
                    f"Postgres Events={metrics['postgres_events']:,},"
                    f"Postgres Pipeline Entity Activity Count={metrics['postgres_pipeline_entity_activity_count']:,},"
                )

                await asyncio.sleep(self.collection_interval)  # Collect every 2 seconds

            except (redis.RedisError, asyncpg.PostgresError) as e:
                logger.error(f"Error collecting metrics: {e}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Unexpected error in metrics collection: {e}")
                await asyncio.sleep(1)


class BetterStackLogsRunner:
    """Create betterstack logs so we can get all logs from the app platform"""

    def __init__(self, project_name: str):
        self.project_name = project_name
        self.sources_created_ids = {}

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
        logger.info(response.json())
        if response.status_code == 201:
            logger.info("Source created successfully")
            response_json = response.json()
            if "data" in response_json:
                if "attributes" in response_json["data"]:
                    if "token" in response_json["data"]["attributes"]:
                        logger.info(
                            "logs token is: "
                            + response_json["data"]["attributes"]["token"]
                        )
                        if "id" in response_json["data"]:
                            name_i = response_json["data"]["attributes"]["name"]
                            self.sources_created_ids[name_i] = response_json["data"][
                                "id"
                            ]
                        return response_json["data"]["attributes"]["token"]
                    else:
                        logger.info(f"No token in response['attributes']")
                else:
                    logger.info(f"No attributes in response['data']")
            else:
                logger.info(f"No data in response")

        else:
            logger.info("Error creating source")
            logger.info(response.text)

    def delete_sources(self):
        BETTERSTACK_TOKEN = os.getenv("BETTERSTACK_TOKEN")

        # https://telemetry.betterstack.com/api/v1/sources/{source_id}
        url = "https://telemetry.betterstack.com/api/v1/sources"

        headers = {"Authorization": f"Bearer {BETTERSTACK_TOKEN}"}

        for name, source_id in self.sources_created_ids.items():
            response = requests.delete(f"{url}/{source_id}", headers=headers)
            if response.status_code == 204:
                logger.info(f"Source {name} with id {source_id} deleted successfully")
            else:
                logger.info(f"Error deleting {name} with source id {source_id}")
                logger.info(response.text)


class EventCollectorAppPlatformRunner:
    """Sets up the App Platform for the event collector  on Digital Ocean"""

    def __init__(self, do_token: str, project_name: str, redis_db_config):
        self.token = do_token
        self.project_name = project_name
        self.name_prefix = "event-collector"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.app_id = None
        self.redis_db_config = redis_db_config

    async def setup_app_platform(
        self, branch: str = "main", betterstack_rsyslog_token: str = None
    ):
        logger.info(
            f"Creating {self.project_name}-{self.name_prefix} App Platform application..."
        )

        event_collector_app_spec = {
            "spec": {
                "name": f"{self.project_name}-{self.name_prefix}",  # Changed underscore to hyphen
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
                            {
                                "key": "USE_TEST_DATA",
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
                        ],
                    }
                ],
            },
            "project_id": os.getenv("DO_PROJECT_ID"),
        }

        # logger.info(
        #     f"About to send spec to do for event collector: {json.dumps(event_collector_app_spec, indent=2)}"
        # )

        response = requests.post(
            "https://api.digitalocean.com/v2/apps",
            headers=self.headers,
            json=event_collector_app_spec,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            logger.info(f"Error response: {response.text}")
            raise

        self.app_id = response.json()["app"]["id"]

        logger.info("Waiting for App Platform application to be ready...")
        while not shutdown_event.is_set():
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            ).json()

            # Print response to debug
            # logger.info(f"Status response: {json.dumps(response, indent=2)}")

            # Change this line to match actual response structure
            app_content = response.get("app")
            # logger.info(f"App content: {app_content}")
            if app_content:
                active_deployment = app_content.get("active_deployment")
                # logger.info(f"Active deployment: {active_deployment}")
                if active_deployment:
                    phase = active_deployment.get("phase")
                    # logger.info(f"Phase: {phase}")
                    if phase == "ACTIVE":
                        logger.info(f"App is active")
                        break
                    else:
                        logger.info(f"Phase is not active")
                else:
                    logger.debug(f"Event Collector active deployment is empty")
            else:
                logger.error(f"App content is empty")

            await asyncio.sleep(10)

        logger.info("App Platform application is ready!")

    async def cleanup_app_platform(self):
        if self.app_id:
            logger.info(
                f"Cleaning up  {self.project_name}-{self.name_prefix} App Platform application..."
            )
            response = requests.delete(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            logger.info("App Platform application cleaned up successfully")


class MonthlyArchiverAppPlatformRunner:
    """Sets up the App Platform for the monthly archiver on Digital Ocean"""

    def __init__(
        self,
        do_token: str,
        project_name: str,
        redis_db_config,
        postgres_pipeline_config,
    ):
        self.token = do_token
        self.project_name = project_name
        self.name_prefix = "monthly-archiver"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.app_id = None
        self.redis_db_config = redis_db_config
        self.postgres_pipeline_config = postgres_pipeline_config

    async def setup_app_platform(
        self, branch: str = "main", betterstack_rsyslog_token: str = None
    ):
        logger.info(
            f"Creating {self.project_name}-{self.name_prefix} App Platform application..."
        )

        monthly_archiver_app_spec = {
            "spec": {
                "name": f"{self.project_name}-{self.name_prefix}",  # Changed underscore to hyphen
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
                        "instance_size_slug": "apps-s-1vcpu-2gb",
                        "dockerfile_path": "backend/monthly_archiver/Dockerfile",
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
                            {
                                "key": "POSTGRES_USER",
                                "value": self.postgres_pipeline_config["user"],
                            },
                            {
                                "key": "POSTGRES_PASSWORD",
                                "value": self.postgres_pipeline_config["password"],
                                "type": "SECRET",
                            },
                            {
                                "key": "POSTGRES_DB",
                                "value": self.postgres_pipeline_config["database"],
                            },
                            {
                                "key": "POSTGRES_HOST",
                                "value": self.postgres_pipeline_config["host"],
                            },
                            {
                                "key": "POSTGRES_PORT",
                                "value": str(self.postgres_pipeline_config["port"]),
                            },
                            {
                                "key": "DAILY_CLEANUP_INTERVAL_SECONDS",
                                "value": "15",
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
            },
            "project_id": os.getenv("DO_PROJECT_ID"),
        }

        # logger.info(
        #     f"About to send spec to do for event collector: {json.dumps(event_collector_app_spec, indent=2)}"
        # )

        response = requests.post(
            "https://api.digitalocean.com/v2/apps",
            headers=self.headers,
            json=monthly_archiver_app_spec,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            logger.info(f"Error response: {response.text}")
            raise

        self.app_id = response.json()["app"]["id"]

        logger.info("Waiting for App Platform application to be ready...")
        while not shutdown_event.is_set():
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            ).json()

            # Print response to debug
            # logger.info(f"Status response: {json.dumps(response, indent=2)}")

            # Change this line to match actual response structure
            app_content = response.get("app")
            # logger.info(f"App content: {app_content}")
            if app_content:
                active_deployment = app_content.get("active_deployment")
                # logger.info(f"Active deployment: {active_deployment}")
                if active_deployment:
                    phase = active_deployment.get("phase")
                    # logger.info(f"Phase: {phase}")
                    if phase == "ACTIVE":
                        logger.info(f"App is active")
                        break
                    else:
                        logger.info(f"Phase is not active")
                else:
                    logger.debug(f"Event Collector active deployment is empty")
            else:
                logger.error(f"App content is empty")

            await asyncio.sleep(10)

        logger.info("App Platform application is ready!")

    async def cleanup_app_platform(self):
        if self.app_id:
            logger.info(
                f"Cleaning up  {self.project_name}-{self.name_prefix} App Platform application..."
            )
            response = requests.delete(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            logger.info("App Platform application cleaned up successfully")


class BatchProcessorAppPlatformRunner:
    """Sets up the App Platform for both the event collector and batch processor on Digital Ocean"""

    def __init__(
        self,
        do_token: str,
        project_name: str,
        redis_db_config,
        postgres_pipeline_config,
    ):
        self.token = do_token
        self.project_name = project_name
        self.name_prefix = "batch-processor"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.app_id = None
        self.redis_db_config = redis_db_config
        self.postgres_pipeline_config = postgres_pipeline_config
        self.current_instance_count = 0

    async def setup_first_batch_processor(
        self, branch: str = "main", betterstack_rsyslog_token: str = None
    ):
        """Start the first batch processor"""
        logger.info("Starting first batch processor...")
        await self.setup_app_platform(
            branch, betterstack_rsyslog_token, instance_count=1
        )
        self.current_instance_count = 1

        # Give it a head start
        head_start = 7
        logger.info(f"Giving first batch processor a {head_start}s head start...")
        await asyncio.sleep(head_start)

    async def scale_batch_processors(self, additional_count: int):
        """Scale up the number of batch processors"""
        if not self.app_id:
            raise ValueError("No batch processor app exists yet")

        if additional_count <= 0:
            await asyncio.sleep(1)
            return

        new_count = self.current_instance_count + additional_count
        logger.info(
            f"Scaling batch processors from {self.current_instance_count} to {new_count}..."
        )

        # Get current app spec
        response = requests.get(
            f"https://api.digitalocean.com/v2/apps/{self.app_id}",
            headers=self.headers,
        )
        response.raise_for_status()
        current_spec = response.json()["app"]["spec"]

        # Update the instance count
        for component in current_spec["workers"]:
            if component["name"] == "worker":
                component["instance_count"] = new_count
                break

        # Update the app
        update_response = requests.put(
            f"https://api.digitalocean.com/v2/apps/{self.app_id}",
            headers=self.headers,
            json={"spec": current_spec},
        )
        update_response.raise_for_status()

        # Wait for scaling to complete
        logger.info("Waiting for scaling to complete...")
        while True:
            status_response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            ).json()

            app_content = status_response.get("app")
            if app_content:
                active_deployment = app_content.get("active_deployment")
                if active_deployment and active_deployment.get("phase") == "ACTIVE":
                    # Verify instance count
                    for component in app_content.get("spec", {}).get("workers", []):
                        if (
                            component["name"] == "worker"
                            and component["instance_count"] == new_count
                        ):
                            logger.success(
                                f"Successfully scaled to {new_count} batch processors"
                            )
                            self.current_instance_count = new_count
                            return

            await asyncio.sleep(10)

    async def setup_app_platform(
        self,
        branch: str = "main",
        betterstack_rsyslog_token: str = None,
        instance_count=1,
    ):
        logger.info(
            f"Creating {self.project_name}-{self.name_prefix} App Platform application..."
        )

        batch_processor_app_spec = {
            "spec": {
                "name": f"{self.project_name}-{self.name_prefix}",  # Changed underscore to hyphen
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
                            {
                                "key": "LOG_LEVEL",
                                "value": "DEBUG",
                            },
                            {
                                "key": "POSTGRES_USER",
                                "value": self.postgres_pipeline_config["user"],
                            },
                            {
                                "key": "POSTGRES_PASSWORD",
                                "value": self.postgres_pipeline_config["password"],
                                "type": "SECRET",
                            },
                            {
                                "key": "POSTGRES_DB",
                                "value": self.postgres_pipeline_config["database"],
                            },
                            {
                                "key": "POSTGRES_HOST",
                                "value": self.postgres_pipeline_config["host"],
                            },
                            {
                                "key": "POSTGRES_PORT",
                                "value": str(self.postgres_pipeline_config["port"]),
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
            },
            "project_id": os.getenv("DO_PROJECT_ID"),
        }

        logger.info(
            f"About to send spec to do for batch_processor: {json.dumps(batch_processor_app_spec, indent=2)}"
        )

        response = requests.post(
            "https://api.digitalocean.com/v2/apps",
            headers=self.headers,
            json=batch_processor_app_spec,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            logger.info(f"Error response: {response.text}")
            raise

        self.app_id = response.json()["app"]["id"]

        logger.info("Waiting for App Platform application to be ready...")
        while True:
            response = requests.get(
                f"https://api.digitalocean.com/v2/apps/{self.app_id}",
                headers=self.headers,
            ).json()

            # Print response to debug
            # logger.info(f"Status response: {json.dumps(response, indent=2)}")

            # Change this line to match actual response structure
            app_content = response.get("app")
            # logger.info(f"App content: {app_content}")
            if app_content:
                active_deployment = app_content.get("active_deployment")
                # logger.info(f"Active deployment: {active_deployment}")
                if active_deployment:
                    phase = active_deployment.get("phase")
                    # logger.info(f"Phase: {phase}")
                    if phase == "ACTIVE":
                        logger.info(f"App is active")
                        break
                    else:
                        logger.info(f"Phase is not active")
                else:
                    logger.debug(f"Batch Processor active deployment is empty")
            else:
                logger.error(f"App content is empty")

            await asyncio.sleep(10)

        logger.info("Batch Processor App Platform application is ready!")

    async def cleanup_app_platform(self):
        if self.app_id:
            logger.info(
                f"Cleaning up  {self.project_name}-{self.name_prefix} App Platform application..."
            )
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
            "size": "db-s-6vcpu-16gb",
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

        logger.info(f"DB info: {db_info}")

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

        logger.info(f"{self.name_prefix} database setup complete!")

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
            "size": "db-s-6vcpu-16gb",  # this is expensive, make sure it gets torn down
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
    metrics_db = PostgresTestRunner(do_token, project_name, "pipeline")
    redis_runner = RedisRunner(do_token, project_name)

    # Setup components
    await asyncio.gather(
        metrics_db.setup_database(project_id),
        redis_runner.setup_database(project_id),
    )

    return metrics_db, redis_runner


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
    logger.info(f"PROJECT_NAME={project_name}")
    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

    events_db, metrics_db, redis_runner = None, None, None
    running_tasks = []
    NUM_BATCH_PROCESSORS = 5
    try:
        # create a better stack logs runner
        betterstack_log_runner = BetterStackLogsRunner(project_name)
        logger.info(f"Created betterstack runner with project name is {project_name}")

        # Setup managed databases
        metrics_db, redis_runner = await setup_infrastructure(
            do_token, project_name, project_id=os.getenv("DO_PROJECT_ID")
        )

        logger.info(f"Redis db config is {redis_runner.db_config}")
        # Setup App Platform for event collector
        logs_token = betterstack_log_runner.create_source("event-collector")
        logger.info(f"Logs token: {logs_token}")
        event_collector_app_runner = EventCollectorAppPlatformRunner(
            do_token, project_name=project_name, redis_db_config=redis_runner.db_config
        )
        await event_collector_app_runner.setup_app_platform(
            branch="full-redesign", betterstack_rsyslog_token=logs_token
        )
        logger.info(f"App runner setup for event collector complete")

        batch_process_app_runner = BatchProcessorAppPlatformRunner(
            do_token,
            project_name=project_name,
            redis_db_config=redis_runner.db_config,
            postgres_pipeline_config=metrics_db.db_config,
        )

        archiver_logs_token = betterstack_log_runner.create_source("monthly-archiver")
        monthly_archiver_app_runner = MonthlyArchiverAppPlatformRunner(
            do_token,
            project_name=project_name,
            redis_db_config=redis_runner.db_config,
            postgres_pipeline_config=metrics_db.db_config,
        )

        await monthly_archiver_app_runner.setup_app_platform(
            branch="full-redesign", betterstack_rsyslog_token=archiver_logs_token
        )

        # Initialize metrics collector
        metrics_collector = MetricsCollector(
            redis_runner.redis_client, project_name, NUM_BATCH_PROCESSORS
        )

        monitoring_tasks = [
            asyncio.create_task(
                metrics_collector.check_redis_empty(redis_runner.redis_client)
            ),
            asyncio.create_task(
                metrics_collector.monitor_redis_items(redis_runner.redis_client)
            ),
            asyncio.create_task(
                metrics_collector.monitor_postgres_events_db(metrics_db.pool)
            ),
        ]
        running_tasks.extend(monitoring_tasks)

        # Wait for queue to fill up
        REDIS_EVENTS_MINIMUM = 2_350_000
        logger.info(
            f"Waiting for Redis queue to accumulate {REDIS_EVENTS_MINIMUM} events..."
        )
        queue_ready = await metrics_collector.wait_for_queue_size(
            redis_client=redis_runner.redis_client,
            target_size=REDIS_EVENTS_MINIMUM,
            check_interval=10,
            timeout=1500,
        )

        if not queue_ready:
            logger.warning(
                "Queue didn't reach target size within timeout, proceeding anyway"
            )

        logger.info(f"Setting start time for metrics collection")

        # if shutdown was triggered, exit early
        if shutdown_event.is_set():
            logger.warning(
                f"Shutdown event triggered, exiting early and skipping batch processor setup"
            )
            return

        logger.info(
            f"Queue is ready with {REDIS_EVENTS_MINIMUM} events, starting to monitor queue progress"
        )
        # Start progress monitoring
        progress_monitor = asyncio.create_task(
            metrics_collector.monitor_queue_progress(
                redis_client=redis_runner.redis_client, target_size=REDIS_EVENTS_MINIMUM
            )
        )
        running_tasks.append(progress_monitor)

        metrics_collector.start_time = time.time()
        get_data_for_graph_task = asyncio.create_task(
            metrics_collector.collect_metrics_history(
                redis_runner.redis_client, metrics_db.pool
            )
        )
        running_tasks.append(get_data_for_graph_task)

        # Start batch processor
        bp_logs_token = betterstack_log_runner.create_source("batch-processor")
        await batch_process_app_runner.setup_first_batch_processor(
            branch="full-redesign", betterstack_rsyslog_token=bp_logs_token
        )
        logger.info("First batch processor started")

        # Scale batch processors
        await batch_process_app_runner.scale_batch_processors(NUM_BATCH_PROCESSORS - 1)

        # Keep running until interrupted or error occurs
        while not shutdown_event.is_set():
            done, pending = await asyncio.wait(
                running_tasks, timeout=7200, return_when=asyncio.FIRST_EXCEPTION
            )

            # Check for exceptions
            for task in done:
                try:
                    await task
                except Exception as e:
                    logger.error(f"Task failed with error: {e}")
                    shutdown_event.set()
                    break

            running_tasks = list(pending)

    finally:
        # Cancel pending tasks
        # Cancel all running tasks
        for task in running_tasks:
            task.cancel()

        if running_tasks:
            await asyncio.gather(*running_tasks, return_exceptions=True)

        cleanup_tasks = [
            events_db.cleanup() if events_db else None,
            metrics_db.cleanup() if metrics_db else None,
            redis_runner.cleanup() if redis_runner else None,
            event_collector_app_runner.cleanup_app_platform()
            if event_collector_app_runner
            else None,
            batch_process_app_runner.cleanup_app_platform()
            if batch_process_app_runner
            else None,
            monthly_archiver_app_runner.cleanup_app_platform()
            if monthly_archiver_app_runner
            else None,
            betterstack_log_runner.delete_sources() if betterstack_log_runner else None,
        ]
        cleanup_tasks = [t for t in cleanup_tasks if t is not None]

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks)

        logger.info("Cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
