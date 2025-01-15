import pandas as pd
import matplotlib.pyplot as plt
import asyncio
import docker
import psycopg2
import redis
import time
from datetime import datetime
import csv
import os
from loguru import logger
import sys


# Configure loguru logger
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add("local_perf_test.log", rotation="100 MB", level="DEBUG")


class LocalPerformanceTest:
    def __init__(self):
        logger.info("Initializing LocalPerformanceTest")
        self.docker_client = docker.from_env()
        self.metrics_dir = "metrics"
        if not os.path.exists(self.metrics_dir):
            os.makedirs(self.metrics_dir)
            logger.info(f"Created metrics directory: {self.metrics_dir}")

        self.csv_filename = f"{self.metrics_dir}/local_perf_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.initialize_csv()
        logger.info(f"Initialized CSV file: {self.csv_filename}")

    def initialize_csv(self):
        with open(self.csv_filename, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp",
                    "redis_items",
                    "postgres_items",
                    "event_collector_ram",
                    "batch_processor_ram",
                    "redis_ram",
                    "postgres_ram",
                    "ingestion_rate",
                    "processing_rate",
                ],
            )
            writer.writeheader()
        logger.debug("CSV file initialized with headers")

    async def start_core_services(self):
        """Start Redis and Postgres services"""
        logger.info("Starting core services (Redis and Postgres)...")
        process = await asyncio.create_subprocess_shell(
            "docker compose up -d redis postgres_pipeline",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            logger.success("Core services started successfully")
        else:
            logger.error(f"Error starting core services: {stderr.decode()}")

        logger.info("Waiting for services to be healthy...")
        await asyncio.sleep(10)  # Wait for services to be healthy

    async def start_event_collector(self):
        """Start the event collector service"""
        logger.info("Starting event collector...")
        process = await asyncio.create_subprocess_shell(
            "docker compose up -d event_collector",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            logger.success("Event collector started successfully")
        else:
            logger.error(f"Error starting event collector: {stderr.decode()}")

    async def start_batch_processor(self):
        """Start the batch processor service"""
        logger.info("Starting batch processor...")
        process = await asyncio.create_subprocess_shell(
            "docker compose up -d batch_processor_leader",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            logger.success("Batch processor started successfully")
        else:
            logger.error(f"Error starting batch processor: {stderr.decode()}")

    async def wait_for_redis_count(self, target_count: int, check_interval: int = 10):
        """Wait until Redis has accumulated the target number of items"""
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        logger.info(f"Waiting for Redis to accumulate {target_count:,} items...")

        last_count = 0
        start_time = time.time()

        while True:
            current_count = redis_client.llen("dvmdash_events")
            elapsed_time = time.time() - start_time

            # Calculate ingestion rate
            if elapsed_time > 0:
                rate = (current_count - last_count) / check_interval
                progress = (current_count / target_count) * 100

                # Create progress bar
                bar_length = 30
                filled_length = int(bar_length * current_count / target_count)
                bar = "=" * filled_length + "-" * (bar_length - filled_length)

                logger.info(
                    f"Progress: [{bar}] {progress:.1f}% | "
                    f"Items: {current_count:,}/{target_count:,} | "
                    f"Rate: {rate:.0f} items/sec"
                )

            if current_count >= target_count:
                logger.success(f"Target count of {target_count:,} items reached!")
                break

            last_count = current_count
            await asyncio.sleep(check_interval)

    def get_container_stats(self, container_name: str) -> dict:
        """Get RAM usage for a specific container"""
        try:
            # Get a list of all running containers
            containers = self.docker_client.containers.list()
            logger.debug(f"Found {len(containers)} running containers")

            # SPECIAL CASE because we want to aggregate stats for all batch processors
            if container_name == "dvmdash-batch_processor":
                # Look for both leader and follower processors
                ram_total = 0
                processor_count = 0
                for c in containers:
                    if "batch-processor" in c.name:  # This will match both types
                        stats = c.stats(stream=False)
                        memory_stats = stats["memory_stats"]
                        usage = memory_stats.get("usage", 0) - memory_stats.get(
                            "stats", {}
                        ).get("cache", 0)
                        ram_total += usage
                        processor_count += 1

                ram_mb = ram_total / (1024 * 1024)  # Convert to MB
                logger.debug(
                    f"Total RAM usage for {processor_count} batch processors: {ram_mb:.1f}MB"
                )
                return {"ram_usage": ram_mb}

            # for all other containers
            container = None
            for c in containers:
                # Check if the container name contains our search string
                if container_name in c.name:
                    container = c
                    logger.debug(f"Found matching container: {c.name}")
                    break

            if not container:
                logger.warning(
                    f"Container {container_name} not found in running containers"
                )
                return {"ram_usage": 0}

            # Get stats
            stats = container.stats(stream=False)
            logger.debug(f"Got stats for {container_name}")

            if "memory_stats" not in stats:
                logger.warning(f"No memory stats available for {container_name}")
                return {"ram_usage": 0}

            memory_stats = stats["memory_stats"]
            # Calculate actual memory usage (total - cache)
            usage = memory_stats.get(
                "usage", 0
            ) - memory_stats.get(  # Total memory usage
                "stats", {}
            ).get(
                "cache", 0
            )  # Remove cache

            ram_mb = usage / (1024 * 1024)  # Convert to MB
            logger.debug(f"RAM usage for {container_name}: {ram_mb:.1f}MB")
            return {"ram_usage": ram_mb}

        except Exception as e:
            logger.error(f"Error getting stats for {container_name}: {e}")
            logger.exception("Full traceback:")
            return {"ram_usage": 0}

    def format_metrics_output(self, metrics: dict) -> str:
        """Format metrics for pretty console output"""

        # Get cleanup timestamps from Redis
        try:
            redis_client = redis.Redis(
                host="localhost", port=6379, decode_responses=True
            )
            daily_ts = redis_client.get("dvmdash_daily_cleanup_timestamp")
            monthly_ts = redis_client.get("dvmdash_monthly_cleanup_timestamp")

            if daily_ts:
                daily_cleanup = datetime.fromtimestamp(float(daily_ts)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                daily_cleanup = "Not set"

            if monthly_ts:
                monthly_cleanup = datetime.fromtimestamp(float(monthly_ts)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                monthly_cleanup = "Not set"

            cleanup_metrics = (
                f"Cleanup Times | "
                f"Daily: {daily_cleanup} | "
                f"Monthly: {monthly_cleanup}"
            )
        except Exception as e:
            logger.error(f"Error getting cleanup timestamps: {e}")
            cleanup_metrics = "Cleanup Times | Error retrieving timestamps"

        ram_metrics = (
            f"RAM Usage (MB) | "
            f"Event Collector: {metrics['event_collector_ram']:.1f} | "
            f"Batch Processor: {metrics['batch_processor_ram']:.1f} | "
            f"Redis: {metrics['redis_ram']:.1f} | "
            f"Postgres: {metrics['postgres_ram']:.1f}"
        )

        queue_metrics = (
            f"Queue Status | "
            f"Redis: {metrics['redis_items']:,} items | "
            f"Postgres: {metrics['postgres_items']:,} items"
        )

        rates = (
            f"Rates | "
            f"Ingestion: {metrics.get('ingestion_rate', 0):.0f} items/sec | "
            f"Processing: {metrics.get('processing_rate', 0):.0f} items/sec"
        )

        return f"\n{queue_metrics}\n{ram_metrics}\n{rates}"

    async def collect_metrics(self):
        """Collect and store metrics"""
        logger.info("Starting metrics collection")
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        postgres_conn = psycopg2.connect(
            dbname="dvmdash_pipeline",
            user="devuser",
            password="devpass",
            host="localhost",
            port=5432,
        )

        last_redis_count = 0
        last_postgres_count = 0
        collection_interval = 5  # seconds

        while True:
            try:
                current_redis_count = redis_client.llen("dvmdash_events")
                current_postgres_count = self.get_postgres_count(postgres_conn)

                # Calculate rates
                ingestion_rate = (
                    current_redis_count - last_redis_count
                ) / collection_interval
                processing_rate = (
                    current_postgres_count - last_postgres_count
                ) / collection_interval

                metrics = {
                    "timestamp": datetime.now().isoformat(),
                    "redis_items": current_redis_count,
                    "postgres_items": current_postgres_count,
                    "event_collector_ram": self.get_container_stats(
                        "dvmdash-event_collector"
                    )["ram_usage"],
                    "batch_processor_ram": self.get_container_stats(
                        "dvmdash-batch_processor"
                    )["ram_usage"],
                    "redis_ram": self.get_container_stats("dvmdash-redis")["ram_usage"],
                    "postgres_ram": self.get_container_stats(
                        "dvmdash-postgres_pipeline"
                    )["ram_usage"],
                    "ingestion_rate": ingestion_rate,
                    "processing_rate": processing_rate,
                }

                # Write to CSV
                with open(self.csv_filename, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=metrics.keys())
                    writer.writerow(metrics)

                # Log formatted metrics
                logger.info(self.format_metrics_output(metrics))

                last_redis_count = current_redis_count
                last_postgres_count = current_postgres_count

                await asyncio.sleep(collection_interval)

            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                await asyncio.sleep(collection_interval)

    def get_postgres_count(self, conn) -> int:
        """Get count of items in Postgres"""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM raw_events")
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting Postgres count: {e}")
            return 0

    def create_performance_plots(self):
        """Create and save performance visualization plots"""
        logger.info("Creating performance visualization...")
        try:
            # Read the CSV file
            df = pd.read_csv(self.csv_filename)

            # Convert timestamp to datetime and calculate seconds from start
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["seconds"] = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds()

            # Create the plot
            plt.figure(figsize=(12, 6))

            # Plot queue size
            plt.subplot(2, 1, 1)
            plt.plot(df["seconds"], df["redis_items"], "b-", label="Redis Queue Size")
            plt.xlabel("Time (seconds)")
            plt.ylabel("Number of Items")
            plt.title("Redis Queue Size Over Time")
            plt.grid(True)

            # Plot processing rate
            plt.subplot(2, 1, 2)
            processing_rate = -df["redis_items"].diff() / df["seconds"].diff()
            smoothed_rate = processing_rate.rolling(window=5).mean()  # Smooth the rate
            plt.plot(df["seconds"], smoothed_rate, "r-", label="Processing Rate")
            plt.xlabel("Time (seconds)")
            plt.ylabel("Items/Second")
            plt.title("Processing Rate Over Time")
            plt.grid(True)

            plt.tight_layout()

            # Save the plot alongside the CSV file
            plot_filename = self.csv_filename.replace(".csv", "_graph.png")
            plt.savefig(plot_filename)
            logger.info(f"Performance graph saved to: {plot_filename}")

            # Show the plot
            plt.show()

        except Exception as e:
            logger.error(f"Error creating performance plots: {e}")
            logger.exception("Full traceback:")

    async def run_test(self, target_redis_items: int = 100_000):
        """Run the complete performance test"""
        logger.info(
            f"Starting performance test with target of {target_redis_items:,} items"
        )
        try:
            # Start core services
            await self.start_core_services()

            # Start event collector
            await self.start_event_collector()

            # Start metrics collection
            logger.info("Starting metrics collection task")
            metrics_task = asyncio.create_task(self.collect_metrics())

            # Wait for Redis to fill up
            await self.wait_for_redis_count(target_redis_items)

            # Start batch processor
            await self.start_batch_processor()

            # Keep running until Redis is empty
            logger.info("Monitoring Redis queue until empty...")
            while True:
                redis_client = redis.Redis(
                    host="localhost", port=6379, decode_responses=True
                )
                if redis_client.llen("dvmdash_events") == 0:
                    logger.success("Redis queue is empty, test complete!")
                    break
                await asyncio.sleep(10)

            # Cancel metrics collection
            logger.info("Cancelling metrics collection")
            metrics_task.cancel()

            # Create and save performance plots
            self.create_performance_plots()

        except Exception as e:
            logger.error(f"Error during test: {e}")
        finally:
            # Cleanup
            logger.info("Cleaning up Docker containers...")
            logger.info("Cleaning up containers and volumes...")
            process = await asyncio.create_subprocess_shell(
                "docker compose --profile all down -v",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                logger.success("Cleanup completed successfully")
            else:
                logger.error(f"Cleanup failed: {stderr.decode()}")
            logger.success(f"Test complete! Metrics saved to: {self.csv_filename}")

            # Create and save performance plots
            self.create_performance_plots()


async def main():
    test = LocalPerformanceTest()
    await test.run_test()


if __name__ == "__main__":
    asyncio.run(main())
