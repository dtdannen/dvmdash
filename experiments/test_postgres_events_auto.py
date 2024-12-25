import asyncio
import json
from datetime import datetime
import os
from typing import Dict
import requests
import asyncpg
import ijson
from loguru import logger
from dotenv import load_dotenv
import time
import random
from asyncio import Queue
import matplotlib.pyplot as plt
import numpy as np
import signal

# handle signal to shutdown so we shutdown gracefully
shutdown_event = asyncio.Event()

load_dotenv()


data = Queue()


class PostgresTestRunner:
    def __init__(self, do_token: str):
        self.token = do_token
        self.db_id = None
        self.db_config = None
        self.pool = None

    async def _init_db_pool(self):
        self.pool = await asyncpg.create_pool(**self.db_config)

    async def setup_database(self, project_id: str = None) -> None:
        """Create and configure DO managed Postgres database"""
        logger.info("Creating managed Postgres database...")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        # Create database cluster
        create_params = {
            "name": f"events-test-{int(time.time())}",
            "engine": "pg",
            "version": "14",
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
        logger.info("Initializing database schema...")
        with open("infrastructure/postgres/events_init.sql", "r") as f:
            schema = f.read()

        async with self.pool.acquire() as conn:
            await conn.execute(schema)

        logger.info("Database setup complete!")

    async def stream_test_data(self, filepath: str, max_events: int = 100000) -> None:
        """Stream test data into database"""
        logger.info(f"Starting to stream {max_events} events from {filepath}")

        events_processed = 0
        batch = []
        batch_size = 10 * random.randint(100, 250)

        with open(filepath, "rb") as f:
            parser = ijson.items(f, "item")

            for event in parser:
                if shutdown_event.is_set():
                    logger.info("Shutting down stream_test_data task...")
                    break

                db_event = {
                    "id": event["id"],
                    "pubkey": event["pubkey"],
                    "created_at": datetime.fromtimestamp(event["created_at"]),
                    "kind": event["kind"],
                    "content": event["content"],
                    "sig": event["sig"],
                    "tags": json.dumps(event["tags"]),
                    "raw_data": json.dumps(event),
                }
                batch.append(db_event)
                events_processed += 1

                if len(batch) >= batch_size:
                    await self._insert_batch(batch)
                    await asyncio.sleep(0.01)
                    batch = []

                if events_processed >= max_events:
                    break

            if batch:
                await self._insert_batch(batch)
                await asyncio.sleep(0.01)

        logger.info(f"Finished processing {events_processed} events")

    async def _insert_batch(self, batch: list) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO raw_events (id, pubkey, created_at, kind, content, sig, tags, raw_data)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (id) DO NOTHING
                """,
                [
                    (
                        event["id"],
                        event["pubkey"],
                        event["created_at"],
                        event["kind"],
                        event["content"],
                        event["sig"],
                        event["tags"],
                        event["raw_data"],
                    )
                    for event in batch
                ],
            )

    async def query_stats(self, stop_limit=50000) -> None:
        """Get event count and most recent events"""
        count = -1
        while count < stop_limit and not shutdown_event.is_set():
            async with self.pool.acquire() as conn:
                # Get total count
                count = await conn.fetchval("SELECT COUNT(*) FROM raw_events")
                logger.info(f"Total events: {count}")

                await data.put(count)
                await asyncio.sleep(1)

        if shutdown_event.is_set():
            logger.info(
                "Shutting down query_stats task... this will take a few seconds"
            )
            for i in range(5):
                logger.info("<some useful shutdown thingy...>")
                await asyncio.sleep(random.randint(1, 3))

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


async def shutdown(runner):
    """Graceful shutdown"""
    logger.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_event.set()


async def main():
    do_token = os.getenv("DO_TOKEN")
    if not do_token:
        raise ValueError("DO_TOKEN environment variable is required")

    project_id = os.getenv("DO_PROJECT_ID")

    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(runner)))

    runner = PostgresTestRunner(do_token)

    try:
        await runner.setup_database(project_id=project_id)
        # Test solution #1 - WORKED!
        tasks = [
            runner.query_stats(stop_limit=50000),
            runner.stream_test_data(
                "backend/event_collector/test_data/dvmdash.prod_events_29NOV2024.json",
                max_events=50000,
            ),
        ]

        # Create the tasks
        running_tasks = [asyncio.create_task(t) for t in tasks]

        # Wait for either tasks to complete or shutdown signal
        done, pending = await asyncio.wait(
            running_tasks, return_when=asyncio.FIRST_COMPLETED
        )

        shutdown_grace_period = 20.0

        # If we get here due to shutdown, handle pending tasks
        if shutdown_event.is_set():
            # Give all pending tasks 7 seconds to clean up concurrently
            try:
                done, still_pending = await asyncio.wait(
                    pending,
                    timeout=shutdown_grace_period,
                    return_when=asyncio.ALL_COMPLETED,
                )

                # Cancel any tasks that didn't finish in time
                for task in still_pending:
                    logger.info(
                        f"Task cleanup timed out after {shutdown_grace_period} seconds, forcing cancellation..."
                    )
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
        else:
            # For non-shutdown cases, cancel immediately
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    finally:
        pass
        # get all the data out of the queue, into a list
        # counts = []
        # while not data.empty():
        #     counts.append(await data.get())
        #
        # data_points = list(counts)
        # # Create x-axis values (indices of the data points)
        # x = np.arange(len(data_points))
        #
        # # Create the line plot
        # plt.figure(figsize=(10, 6))  # Set the figure size
        # plt.plot(x, data_points, "-")  # '-' specifies a solid line
        #
        # # Customize the plot
        # plt.title("Data Points Over Time")
        # plt.xlabel("Index")
        # plt.ylabel("Value")
        # plt.grid(True)  # Add grid lines
        #
        # # Display the plot
        # plt.show()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
