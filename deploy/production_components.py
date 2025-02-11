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
            "size": "2-4-80-dd",
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
            "size": "1-2-30",
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
