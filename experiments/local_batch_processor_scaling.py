import pandas as pd
import matplotlib.pyplot as plt
import asyncio
import docker
import psycopg2
import redis
import time
from datetime import datetime, timezone
import csv
import os
from loguru import logger
import sys
import json
import platform


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
    def __init__(self, num_batch_processors: int = 1):
        logger.info("Initializing LocalPerformanceTest")
        self.docker_client = docker.from_env()

        # Base metrics directory
        self.metrics_dir = "metrics"
        if not os.path.exists(self.metrics_dir):
            os.makedirs(self.metrics_dir)
            logger.info(f"Created base metrics directory: {self.metrics_dir}")

        # Create run-specific directory
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = os.path.join(self.metrics_dir, f"run_{self.run_timestamp}")
        os.makedirs(self.run_dir)
        logger.info(f"Created run directory: {self.run_dir}")

        # Initialize CSV in run directory
        self.csv_filename = os.path.join(self.run_dir, "metrics.csv")
        self.initialize_csv()
        logger.info(f"Initialized CSV file: {self.csv_filename}")

        self.monthly_update_timestamps = []

        self.num_batch_processors = num_batch_processors

    def get_monthly_activity_data(self):
        """Query and return all data from the monthly_activity table"""
        try:
            conn = psycopg2.connect(
                dbname="dvmdash_pipeline",
                user="devuser",
                password="devpass",
                host="localhost",
                port=5432,
            )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        year_month,
                        total_requests,
                        total_responses,
                        unique_dvms,
                        unique_kinds,
                        unique_users,
                        dvm_activity,
                        kind_activity,
                        created_at
                    FROM monthly_activity
                    ORDER BY year_month ASC
                """
                )

                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()

                # Convert to list of dicts and handle JSONB fields
                data = []
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    # Convert datetime objects to ISO format strings
                    row_dict["created_at"] = row_dict["created_at"].isoformat()
                    data.append(row_dict)

                return data

        except Exception as e:
            logger.error(f"Error querying monthly_activity table: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def save_run_info(self):
        """Save basic information about this test run in both JSON and markdown formats"""

        monthly_data = self.get_monthly_activity_data()

        info = {
            "start_time": self.run_timestamp,
            "python_version": sys.version,
            "platform": sys.platform,
            "docker_compose_services": [
                "redis",
                "postgres_pipeline",
                "event_collector",
                "batch_processor",
                "monthly_archiver",
            ],
            "host_info": {
                "os": os.name,
                "processor": platform.processor(),
                "machine": platform.machine(),
            },
            "monthly_activity": monthly_data,
        }

        # Save JSON version
        info_file = os.path.join(self.run_dir, "run_info.json")
        with open(info_file, "w") as f:
            json.dump(info, f, indent=2)

        # Create markdown version
        md_content = f"""# Performance Test Run Info
    
        ## Test Details
        - **Start Time**: {self.run_timestamp}
        - **Run Directory**: {self.run_dir}
    
        ## Environment
        - **Python Version**: ```{sys.version.split()[0]}```
        - **Full Python Build**: ```{sys.version}```
        - **Platform**: {sys.platform}
        - **OS**: {os.name}
        - **Processor**: {platform.processor()}
        - **Machine Architecture**: {platform.machine()}
    
        ## Services
        The following Docker Compose services are used in this test:
        """
        # Add services list
        for service in info["docker_compose_services"]:
            md_content += f"- {service}\n"

        md_content += """
        ## Files
        The following files are generated during the test:
        - `metrics.csv`: Raw metrics data collected during the test
        - `performance.png`: Visualization of Redis queue size and processing rate
        - `performance.pdf`: High-quality PDF version of the performance plots
        - `plot_data.json`: Raw plot data for further analysis
        - `run_info.json`: Machine-readable version of this information
    
        ## Notes
        - All timestamps are in UTC
        - Performance plots include vertical markers for monthly update events
        - Processing rate is smoothed using a 5-point rolling average
        
        ## Monthly Activity Data
        Below is the current state of the monthly_activity table:
        
        | Month | Requests | Responses | DVMs | Kinds | Users |
        |-------|----------|-----------|------|-------|-------|
        """

        # Add monthly activity data to markdown
        if monthly_data:
            for row in monthly_data:
                md_content += f"| {row['year_month']} | {row['total_requests']:,} | {row['total_responses']:,} | {row['unique_dvms']:,} | {row['unique_kinds']:,} | {row['unique_users']:,} |\n"
        else:
            md_content += "| N/A |\n"

        md_content += "\n\nDetailed monthly activity data including DVM and kind activity is available in the JSON file."

        md_content += """
        """

        # Save markdown version
        md_file = os.path.join(self.run_dir, "run_info.md")
        with open(md_file, "w") as f:
            f.write(md_content)

        logger.info(f"Saved run info to: {info_file} and {md_file}")

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

    async def start_first_batch_processor(self):
        """Start one batch processor and give it a few second head start to prevent problems setting the initial
        month/year in redis"""
        head_start = 5
        logger.info(
            f"Starting first batch processor with a head start of {head_start}s..."
        )
        process = await asyncio.create_subprocess_shell(
            f"docker compose up -d batch_processor",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            logger.success(
                f"First batch processor started successfully, now waiting {head_start} seconds"
            )
            # Log the stdout in case there's useful info
            if stdout:
                logger.debug(f"Batch processor stdout: {stdout.decode()}")
            await asyncio.sleep(head_start)
        else:
            logger.error(f"Error starting batch processors: {stderr.decode()}")
            # Log the stdout as well in case of error
            if stdout:
                logger.error(f"Batch processor stdout: {stdout.decode()}")

    async def start_additional_batch_processors(self, count_to_add: int = 1):
        """Start additional batch processor instances"""
        # Get current container count
        logger.info(f"Starting to add {count_to_add} batch processor(s)...")
        process = await asyncio.create_subprocess_shell(
            "docker compose ps -q batch_processor | wc -l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        current_count = int(stdout.decode().strip())
        logger.info(f"Current batch processor count: {current_count}")
        new_count = current_count + count_to_add

        logger.info(
            f"Adding {count_to_add} batch processor(s) for a total of {new_count}..."
        )
        process = await asyncio.create_subprocess_shell(
            f"docker compose up -d --scale batch_processor={new_count} batch_processor",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            logger.success(
                f"{count_to_add} batch processor{'s' if count_to_add > 1 else ''} started successfully"
            )
        else:
            logger.error(f"Error starting batch processors: {stderr.decode()}")

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
                    if "batch_processor" in c.name:  # This will match both types
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

            # Convert timestamp to datetime in UTC
            df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC")
            experiment_start_time = df["timestamp"].min()

            # Calculate seconds from start
            df["seconds"] = (df["timestamp"] - experiment_start_time).dt.total_seconds()

            # Create the plot
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

            # Plot queue size
            ax1.plot(df["seconds"], df["redis_items"], "b-", label="Redis Queue Size")
            ax1.set_xlabel("Time (seconds)")
            ax1.set_ylabel("Number of Items")
            ax1.set_title("Redis Queue Size Over Time (UTC)")
            ax1.grid(True)
            ax1.legend()

            # Plot processing rate
            processing_rate = -df["redis_items"].diff() / df["seconds"].diff()
            smoothed_rate = processing_rate.rolling(window=5).mean()
            ax2.plot(df["seconds"], smoothed_rate, "r-", label="Processing Rate")
            ax2.set_xlabel("Time (seconds)")
            ax2.set_ylabel("Items/Second")
            ax2.set_title("Processing Rate Over Time (UTC)")
            ax2.grid(True)
            ax2.legend()

            # Debug monthly update timestamps
            logger.info("\nMonthly Update Timestamp Analysis:")
            logger.info(f"Experiment start time: {experiment_start_time} UTC")
            logger.info(
                f"Number of monthly updates: {len(self.monthly_update_timestamps)}"
            )

            # Add vertical lines for monthly updates
            if self.monthly_update_timestamps:
                for i, cleanup_time in enumerate(self.monthly_update_timestamps):
                    # Get the cleanup time relative to experiment start
                    cleanup_time = cleanup_time.replace(tzinfo=timezone.utc)
                    cleanup_minute = cleanup_time.minute
                    cleanup_second = cleanup_time.second

                    # Create a relative time based on minutes/seconds from start
                    experiment_minute = experiment_start_time.minute
                    experiment_second = experiment_start_time.second

                    # Calculate relative seconds (ignoring the date/hour difference)
                    seconds_from_start = (cleanup_minute - experiment_minute) * 60 + (
                        cleanup_second - experiment_second
                    )

                    logger.info(f"\nUpdate {i + 1}:")
                    logger.info(f"  Cleanup time: {cleanup_time} UTC")
                    logger.info(f"  Seconds from start: {seconds_from_start:.2f}")
                    logger.info(f"  Current x-axis range: {ax1.get_xlim()}")

                    ax1.axvline(
                        x=seconds_from_start, color="g", linestyle="--", alpha=0.5
                    )
                    ax2.axvline(
                        x=seconds_from_start, color="g", linestyle="--", alpha=0.5
                    )
                    # ax1.annotate(
                    #     f"Monthly Cleanup @ {cleanup_time.strftime('%S')}s",
                    #     xy=(seconds_from_start, ax1.get_ylim()[1]),
                    #     xytext=(10, 10),
                    #     textcoords="offset points",
                    #     rotation=90,
                    #     color="green",
                    #     alpha=0.7,
                    # )

            # After creating the plots, before plt.tight_layout()
            # Set x-axis ticks every 20 seconds
            from matplotlib.ticker import MultipleLocator

            # For the first plot (queue size)
            ax1.xaxis.set_major_locator(
                MultipleLocator(20)
            )  # Major ticks every 20 seconds
            ax1.xaxis.set_minor_locator(
                MultipleLocator(5)
            )  # Minor ticks every 5 seconds
            ax1.grid(True, which="major", linestyle="-")
            ax1.grid(True, which="minor", linestyle=":", alpha=0.5)

            # For the second plot (processing rate)
            ax2.xaxis.set_major_locator(
                MultipleLocator(20)
            )  # Major ticks every 20 seconds
            ax2.xaxis.set_minor_locator(
                MultipleLocator(5)
            )  # Minor ticks every 5 seconds
            ax2.grid(True, which="major", linestyle="-")
            ax2.grid(True, which="minor", linestyle=":", alpha=0.5)

            # Rotate x-axis labels for better readability
            ax1.tick_params(axis="x", rotation=45)
            ax2.tick_params(axis="x", rotation=45)

            plt.tight_layout()

            # Save multiple plot formats
            base_plot_filename = os.path.join(self.run_dir, "performance")
            plt.savefig(f"{base_plot_filename}.png")
            plt.savefig(
                f"{base_plot_filename}.pdf"
            )  # Also save as PDF for higher quality
            logger.info(f"Performance graphs saved to: {base_plot_filename}.png/pdf")

            # Save raw plot data
            plot_data = {
                "seconds": df["seconds"].tolist(),
                "redis_items": df["redis_items"].tolist(),
                "processing_rate": smoothed_rate.tolist(),
                "monthly_updates": [
                    (cleanup_time.timestamp() - experiment_start_time.timestamp())
                    for cleanup_time in self.monthly_update_timestamps
                    if cleanup_time.tzinfo
                ],
            }
            with open(os.path.join(self.run_dir, "plot_data.json"), "w") as f:
                json.dump(plot_data, f, indent=2)

            # Show the plot
            # plt.show()

        except Exception as e:
            logger.error(f"Error creating performance plots: {e}")
            logger.exception("Full traceback:")

    async def start_monthly_archiver(self):
        """Start the monthly archiver service"""
        logger.info("Starting monthly archiver...")
        process = await asyncio.create_subprocess_shell(
            "docker compose up -d monthly_archiver",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            logger.success("Monthly archiver started successfully")
        else:
            logger.error(f"Error starting monthly archiver: {stderr.decode()}")

    async def monitor_redis_state(self):
        """Monitor and print Redis state related to backup process"""
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        previous_last_cleanup = None

        while True:
            try:
                # Get state from Redis
                state_json = redis_client.get("dvmdash_state")
                if not state_json:
                    logger.warning("No state found in Redis")
                    await asyncio.sleep(2)
                    continue

                state = json.loads(state_json)

                # Check for monthly update completion
                last_cleanup = state.get("last_monthly_cleanup_completed")
                if last_cleanup and last_cleanup != previous_last_cleanup:
                    cleanup_time = datetime.fromisoformat(last_cleanup)
                    if not cleanup_time.tzinfo:  # Ensure UTC timezone
                        cleanup_time = cleanup_time.replace(tzinfo=timezone.utc)
                    self.monthly_update_timestamps.append(cleanup_time)
                    logger.info(
                        f"Detected monthly update completion at {cleanup_time} UTC"
                    )
                previous_last_cleanup = last_cleanup

                # Get lock info
                lock_exists = redis_client.exists("dvmdash_monthly_cleanup_lock")
                lock_value = (
                    redis_client.get("dvmdash_monthly_cleanup_lock")
                    if lock_exists
                    else None
                )

                cleanup_info = state.get("cleanup", {})
                state_str = (
                    f"Redis State: Year/Month: {state.get('year')}/{state.get('month')} "
                    f"| Last Cleanup: {last_cleanup} "
                    f"| Cleanup Status: [In Progress: {cleanup_info.get('in_progress', False)}, "
                    f"Requested: {cleanup_info.get('requested', False)}, "
                    f"Requested By: {cleanup_info.get('requested_by', 'None')}, "
                    f"Started At: {cleanup_info.get('started_at', 'None')}] "
                    f"| Lock Status: [Lock Exists: {lock_exists}, Lock Value: {lock_value}]"
                )

                logger.info(state_str)

            except Exception as e:
                logger.error(f"Error monitoring Redis state: {e}")

            await asyncio.sleep(2)

    async def run_test(self, target_redis_items: int = 2_400_000):
        """Run the complete performance test"""
        logger.info(
            f"Starting performance test with target of {target_redis_items:,} items"
        )
        try:
            # Start core services
            await self.start_core_services()

            # Start monitoring Redis state
            logger.info("Starting Redis state monitoring")
            state_monitor_task = asyncio.create_task(self.monitor_redis_state())

            # Start event collector
            await self.start_event_collector()

            # Start monthly archiver
            await self.start_monthly_archiver()

            # Start metrics collection
            logger.info("Starting metrics collection task")
            metrics_task = asyncio.create_task(self.collect_metrics())

            # Wait for Redis to fill up
            await self.wait_for_redis_count(target_redis_items)

            # Start the first batch processor
            await self.start_first_batch_processor()

            # Start additional batch processors
            await self.start_additional_batch_processors(self.num_batch_processors - 1)

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

            # Cancel tasks
            logger.info("Cancelling monitoring tasks")
            metrics_task.cancel()
            state_monitor_task.cancel()

            self.save_run_info()

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
            # self.create_performance_plots()


async def main():
    num_batch_processors = 1
    if len(sys.argv) > 1:
        num_batch_processors = int(sys.argv[1])

    test = LocalPerformanceTest(num_batch_processors)
    await test.run_test()


if __name__ == "__main__":
    asyncio.run(main())
