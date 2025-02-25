import asyncio
import sys
import nostr_sdk
import json
import os
import re
from datetime import datetime
from pathlib import Path
import loguru
from nostr_sdk import (
    Keys,
    Client,
    Filter,
    HandleNotification,
    Timestamp,
    LogLevel,
    Kind,
    Event,
)
import traceback
import argparse
import datetime
import time
import yaml
import redis
import tempfile
import aiohttp
from redis import Redis
from typing import Optional, Tuple, AsyncIterator, Dict

# print all the env variables to the console, to see what we start with:
print("Environment variables:")
for key, value in os.environ.items():
    print(f"{key}={value}")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Limit on event size, currently because of limits with REDIS on digital ocean
MAX_EVENT_SIZE_MB = 200  # Maximum event size in MB

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
NOSTR_LOG_LEVEL = os.getenv("NOSTR_LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger = loguru.logger
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)
nostr_sdk.init_logger(getattr(LogLevel, NOSTR_LOG_LEVEL))


RELAYS = os.getenv("RELAYS", "wss://relay.dvmdash.live").split(",")


def load_dvm_config():
    """Load DVM configuration from YAML file. Raises exceptions if file is not found or invalid."""

    # Log the current working directory
    logger.debug(f"Current working directory: {os.getcwd()}")

    config_path = Path("/app/backend/shared/dvm/config/dvm_kinds.yaml")

    if not config_path.exists():
        raise FileNotFoundError(f"Required config file not found at: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if not config:
        raise ValueError(f"Config file is empty: {config_path}")

    # Validate required fields
    required_fields = ["known_kinds", "ranges"]
    missing_fields = [field for field in required_fields if field not in config]
    if missing_fields:
        raise ValueError(
            f"Missing required fields in config: {', '.join(missing_fields)}"
        )

    # Validate ranges structure
    required_range_fields = ["request", "result"]
    for range_field in required_range_fields:
        if range_field not in config["ranges"]:
            raise ValueError(f"Missing required range field: {range_field}")
        if (
            "start" not in config["ranges"][range_field]
            or "end" not in config["ranges"][range_field]
        ):
            raise ValueError(f"Range {range_field} missing start or end value")

    return config


def get_relevant_kinds() -> list[Kind]:
    """Get relevant kinds from config file. Will raise exceptions if config is invalid."""
    try:
        config = load_dvm_config()

        # Get explicitly known kinds
        known_kinds = [k["kind"] for k in config["known_kinds"]]

        # Generate ranges
        request_range = range(
            config["ranges"]["request"]["start"], config["ranges"]["request"]["end"]
        )
        result_range = range(
            config["ranges"]["result"]["start"], config["ranges"]["result"]["end"]
        )

        # Get excluded kinds
        excluded_kinds = {k["kind"] for k in config.get("excluded_kinds", [])}

        # Combine all kinds
        all_kinds = set(known_kinds + list(request_range) + list(result_range))

        # Remove excluded kinds
        valid_kinds = all_kinds - excluded_kinds

        logger.info(
            f"Loaded {len(valid_kinds)} valid kinds, and excluding kinds: {excluded_kinds}"
        )

        return [Kind(k) for k in valid_kinds]
    except Exception as e:
        logger.error(f"Failed to get relevant kinds: {str(e)}")
        raise


# This will now raise an error if the config file can't be found or is invalid
RELEVANT_KINDS = get_relevant_kinds()


def parse_filename_date(filename: str) -> tuple[int, int]:
    """Parse year and month from filename like dvm_data_2024_nov.json"""
    pattern = r'dvm_data_(\d{4})_([a-zA-Z]+)\.json'
    match = re.match(pattern, filename)
    if not match:
        raise ValueError(f"Invalid filename format: {filename}")
    
    year = int(match.group(1))
    month_str = match.group(2).lower()
    
    # Convert month name to number
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    month = month_map.get(month_str[:3])
    if month is None:
        raise ValueError(f"Invalid month in filename: {filename}")
        
    return year, month

async def get_historical_data_urls(historical_months: Optional[int] = None) -> list[str]:
    """
    Get historical data files from CDN, sorted by date.
    If historical_months is set, returns only the most recent X months of data.
    """
    base_url = 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com'
    
    # For now, we'll use a list of known files since we can't list bucket contents directly
    # This will be replaced with actual bucket listing when available
    files = []
    
    # Generate possible filenames for the last few years
    years = range(2023, 2026)  # 2023-2025
    months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    
    async with aiohttp.ClientSession() as session:
        for year in years:
            for month in months:
                filename = f'dvm_data_{year}_{month}.json'
                url = f'{base_url}/{filename}'
                
                try:
                    # Just check if file exists with HEAD request
                    async with session.head(url) as response:
                        if response.status == 200:
                            files.append(filename)
                except Exception:
                    continue  # Skip if file doesn't exist
    
    # Sort files by date
    def sort_key(filename):
        try:
            year, month = parse_filename_date(filename)
            return year * 100 + month  # This creates a sortable integer like 202401
        except ValueError:
            return float('inf')  # Put invalid filenames at the end
            
    sorted_files = sorted(files, key=sort_key, reverse=True)  # Sort newest first
    
    # If historical_months is set, limit to most recent X months
    if historical_months is not None and historical_months > 0:
        sorted_files = sorted_files[:historical_months]
        
    # Re-sort chronologically for processing
    sorted_files.sort(key=sort_key)
    
    return [f'{base_url}/{filename}' for filename in sorted_files]

class HistoricalDataLoader:
    """
    Loads historical data from a MongoDB JSON export file and simulates real-time event ingestion
    by feeding events to Redis queue in batches. Uses streaming to handle large files efficiently.
    """

    def __init__(
        self,
        redis_client,
        urls: Optional[list[str]] = None,
        batch_size: int = 10000,
        delay_between_batches: float = 0.05,
        deduplicator=None,
        max_batches: Optional[int] = None,
    ):
        self.redis = redis_client
        self.urls = urls
        self._urls_initialized = False
        self.batch_size = batch_size
        self.delay_between_batches = delay_between_batches
        self.deduplicator = deduplicator
        self.max_batches = max_batches
        self.events_processed = 0
        self.events_duplicate = 0
        self.batches_processed = 0
        self.last_header_time = 0
        self.header_interval = 20

    async def download_file(
        self, url: str, max_retries: int = 3, timeout: int = 600
    ) -> Path:
        logger.info(f"Downloading file from {url}")
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        temp_path = Path(temp_file.name)

        for attempt in range(max_retries):
            try:
                timeout_client = aiohttp.ClientTimeout(
                    total=timeout, connect=60, sock_read=300
                )
                async with aiohttp.ClientSession(timeout=timeout_client) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        with open(temp_path, "wb") as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                return temp_path
            except Exception as e:
                temp_file.close()
                if temp_path.exists():
                    os.unlink(temp_path)
                if attempt == max_retries - 1:
                    raise Exception(f"Failed to download file from {url}: {str(e)}")
                logger.warning(f"Error downloading {url}, attempt {attempt + 1}: {e}")
                await asyncio.sleep(5 * (attempt + 1))

        raise Exception(
            f"Failed to download file from {url} after {max_retries} attempts"
        )

    async def _initialize_urls(self):
        """Initialize URLs if not provided"""
        if not self._urls_initialized:
            if not self.urls:
                self.urls = await get_historical_data_urls()
            self._urls_initialized = True

    async def process_events(self) -> None:
        """Process events from all URLs sequentially."""
        await self._initialize_urls()
        for url in self.urls:
            logger.debug(f"Starting to process events from {url}")
            temp_path = None

            try:
                # Download current file
                temp_path = await self.download_file(url)

                # Process the downloaded file
                async for batch in self._read_batches(temp_path):
                    batch_duplicates = 0
                    batch_processed = 0

                    for event in batch:
                        if Kind(int(event["kind"])) in RELEVANT_KINDS:
                            # Check for duplicate if deduplicator is configured
                            is_duplicate = False
                            if self.deduplicator:
                                is_duplicate = self.deduplicator.check_duplicate(
                                    event["id"]
                                )

                            if not is_duplicate:
                                # Add to processing queue if not duplicate
                                self.redis.rpush("dvmdash_events", json.dumps(event))
                                batch_processed += 1
                            else:
                                batch_duplicates += 1
                        else:
                            logger.debug(f"Skipping irrelevant event: {event['kind']}")

                    self.events_processed += batch_processed
                    self.events_duplicate += batch_duplicates
                    self.batches_processed += 1

                    await self._print_stats()

                    # Simulate real-time ingestion with delay
                    await asyncio.sleep(self.delay_between_batches)

                    if self.max_batches and self.batches_processed >= self.max_batches:
                        logger.info(
                            f"\nReached maximum batch limit of {self.max_batches}"
                        )
                        return

                logger.debug(f"Completed processing events from {url}")

            except Exception as e:
                logger.error(f"Error processing URL {url}: {e}")
                raise
            finally:
                # Clean up temp file
                if temp_path and temp_path.exists():
                    try:
                        os.unlink(temp_path)
                    except Exception as e:
                        logger.error(f"Error cleaning up temp file {temp_path}: {e}")

    async def process_events_parallel(self, max_concurrent: int = 1) -> None:
        """Process multiple files concurrently with bounded concurrency."""
        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = []

        async def process_url(url: str, max_retries: int = 3):
            async with semaphore:
                logger.info(f"Starting to process events from {url}")
                temp_path = None

                for attempt in range(max_retries):
                    try:
                        temp_path = await self.download_file(url)
                        async for batch in self._read_batches(temp_path):
                            await self._process_batch(batch)
                        logger.debug(f"Successfully processed {url}")
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error(
                                f"Failed to process {url} after {max_retries} attempts: {e}"
                            )
                            raise
                        logger.warning(
                            f"Error processing {url}, attempt {attempt + 1} of {max_retries}: {e}"
                        )
                        await asyncio.sleep(5 * (attempt + 1))  # Exponential backoff
                    finally:
                        if temp_path and temp_path.exists():
                            try:
                                os.unlink(temp_path)
                            except Exception as e:
                                logger.error(
                                    f"Error cleaning up temp file {temp_path}: {e}"
                                )

        # Create tasks for all URLs and process in parallel
        # for url in self.urls:
        #     tasks.append(asyncio.create_task(process_url(url)))

        # sequential processing for testing that monthly cleanups are working
        for url in self.urls:
            await process_url(url)

        # # Wait for all tasks to complete
        # await asyncio.gather(
        #     *tasks, return_exceptions=True
        # )  # Allow some URLs to fail without stopping everything

    async def _process_batch(self, batch: list[Dict]) -> None:
        """Process a batch of events more efficiently."""
        logger.debug(f"Processing batch of {len(batch)} events...")
        start_time = time.time()

        # Convert RELEVANT_KINDS to a set of integers for faster lookup
        relevant_kinds_set = {k.as_u16() for k in RELEVANT_KINDS}
        logger.debug("relevant_kinds_set", relevant_kinds_set)

        # First pass - fast filtering of relevant events
        potentially_relevant = [
            event for event in batch if int(event["kind"]) in relevant_kinds_set
        ]

        if not potentially_relevant:
            logger.debug(f"No relevant events found in batch of {len(batch)}")
            return

        # Chunk the work for concurrent processing
        chunk_size = 1000
        chunks = [
            potentially_relevant[i : i + chunk_size]
            for i in range(0, len(potentially_relevant), chunk_size)
        ]

        async def process_chunk(events):
            relevant = []
            duplicates = 0

            # Check duplicates in a single pipeline
            if self.deduplicator:
                with self.redis.pipeline() as pipe:
                    for event in events:
                        self.deduplicator._add_to_pipeline(pipe, event["id"])
                    results = pipe.execute()

                    # results come in pairs (sadd result, zadd result)
                    for i, event in enumerate(events):
                        is_new = results[i * 2]  # Get sadd result
                        if is_new:
                            relevant.append(event)
                        else:
                            duplicates += 1
            else:
                relevant = events

            return relevant, duplicates

        # Process chunks concurrently
        logger.debug(f"Processing {len(chunks)} chunks concurrently...")
        tasks = [process_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks)

        # Combine results
        relevant_events = []
        total_duplicates = 0
        for chunk_relevant, chunk_duplicates in results:
            relevant_events.extend(chunk_relevant)
            total_duplicates += chunk_duplicates

        logger.info(
            f"Took {time.time()-start_time}s to check {len(relevant_events)} relevant events out of {len(batch)}"
        )

        if relevant_events:
            # Pipeline the Redis write operations
            with self.redis.pipeline() as pipe:
                for event in relevant_events:
                    event_json = json.dumps(event)
                    size_mb = len(event_json.encode("utf-8")) / (1024 * 1024)

                    if size_mb > 1:  # 100MB limit
                        logger.warning(
                            f"Event (id {event['id'] if 'id' in event else '<no-id-found>'})"
                            f" size exceeds limit: {size_mb:.2f}MB, skipping"
                        )
                        continue

                    pipe.rpush("dvmdash_events", event_json)
                pipe.execute()

            self.events_processed += len(relevant_events)
            self.events_duplicate += total_duplicates
            self.batches_processed += 1
            logger.debug(
                f"Processed batch of {len(relevant_events)} events and ignored {total_duplicates} duplicates"
            )
            await self._print_stats()

        if self.delay_between_batches > 0:
            await asyncio.sleep(self.delay_between_batches)

        if self.max_batches and self.batches_processed >= self.max_batches:
            logger.info(f"\nReached maximum batch limit of {self.max_batches}")
            return

    async def _read_batches(self, filepath: Path) -> AsyncIterator[list[Dict]]:
        """Read MongoDB export JSON file in batches using ijson for memory efficiency."""
        try:
            import ijson  # Import here to keep it optional

            logger.debug("Starting streaming JSON processing...")
            current_batch = []

            with open(filepath, "rb") as f:  # Open in binary mode for ijson
                # MongoDB exports are arrays of objects
                parser = ijson.items(f, "item")

                for event in parser:
                    current_batch.append(event)

                    if len(current_batch) >= self.batch_size:
                        yield current_batch
                        current_batch = []

                        if (
                            self.max_batches
                            and self.batches_processed + 1 >= self.max_batches
                        ):
                            break

            # Yield any remaining events
            if current_batch and (
                not self.max_batches or self.batches_processed < self.max_batches
            ):
                yield current_batch

        except ImportError:
            logger.error("ijson package is required for streaming JSON processing")
            logger.error("Please install it with: pip install ijson")
            raise
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            raise

    async def _print_stats(self) -> None:
        """Print processing statistics."""
        current_time = time.time()

        if (
            self.events_processed % self.header_interval == 0
            or current_time - self.last_header_time > 10
        ):
            header = (
                f"{'Time':^12}|{'Processed':^15}|{'Duplicates':^15}|{'Batches':^10}"
            )
            logger.debug(header)
            logger.debug("=" * len(header))
            self.last_header_time = current_time

        current_time_str = time.strftime("%H:%M:%S")
        logger.debug(
            f"{current_time_str:^12}|{self.events_processed:^15d}|"
            f"{self.events_duplicate:^15d}|{self.batches_processed:^10d}"
        )


class EventDeduplicator:
    def __init__(
        self,
        redis_client: redis.Redis,
        max_events: int = 1_000_000,
        cleanup_threshold: float = 0.98,
    ):
        self.redis = redis_client
        self.set_key = "dvmdash_processed_events"
        self.zset_key = "dvmdash_event_timestamps"
        self.max_events = max_events
        self.cleanup_threshold = cleanup_threshold

    def _get_current_size(self) -> int:
        return self.redis.scard(self.set_key)

    def _needs_cleanup(self) -> bool:
        current_size = self._get_current_size()
        return current_size >= (self.max_events * self.cleanup_threshold)

    def _cleanup_oldest_events(self) -> Tuple[int, int]:
        try:
            current_size = self._get_current_size()
            if current_size <= self.max_events:
                return 0, current_size

            target_size = int(self.max_events * 0.95)
            to_remove = current_size - target_size

            oldest_events = self.redis.zrange(
                self.zset_key,
                0,
                to_remove - 1,
                withscores=True,
            )

            if not oldest_events:
                return 0, current_size

            with self.redis.pipeline() as pipe:
                pipe.srem(self.set_key, *[event[0] for event in oldest_events])
                pipe.zremrangebyrank(self.zset_key, 0, to_remove - 1)
                pipe.execute()

            new_size = self._get_current_size()
            logger.debug(
                f"Cleaned up {len(oldest_events)} events. New size: {new_size:,}"
            )
            return len(oldest_events), new_size

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0, self._get_current_size()

    def check_duplicate(self, event_id: str) -> bool:
        """
        Check if event is duplicate and add to tracking if not.
        Returns True if duplicate, False if new.
        """
        try:
            timestamp = time.time()

            with self.redis.pipeline() as pipe:
                # Try to add to set and sorted set
                pipe.sadd(self.set_key, event_id)
                pipe.zadd(self.zset_key, {event_id: timestamp})
                results = pipe.execute()

                is_new = results[0]

                # Cleanup if needed
                if is_new and self._needs_cleanup():
                    removed, new_size = self._cleanup_oldest_events()
                    if removed > 0:
                        logger.debug(
                            f"Cleanup triggered. Removed {removed:,} events. New size: {new_size:,}"
                        )

                return not is_new

        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False

    def _add_to_pipeline(self, pipe, event_id: str):
        """Add deduplication checks to an existing pipeline."""
        timestamp = time.time()
        pipe.sadd(self.set_key, event_id)
        pipe.zadd(self.zset_key, {event_id: timestamp})


class NotificationHandler(HandleNotification):
    def __init__(self):
        self.events_processed = 0
        self.events_duplicate = 0
        self.last_header_time = 0
        self.header_interval = 20

        # Initialize Redis connection and deduplicator
        self.redis = redis.from_url(REDIS_URL)
        self.deduplicator = EventDeduplicator(self.redis)

    async def handle(self, relay_url, subscription_id, event: Event):
        if event.kind() in RELEVANT_KINDS:
            try:
                event_json = json.loads(event.as_json())
                event_id = event_json["id"]

                # Check for duplicate before processing
                is_duplicate = self.deduplicator.check_duplicate(event_id)

                if not is_duplicate:
                    # Only add to processing queue if not duplicate
                    self.redis.rpush("dvmdash_events", json.dumps(event_json))
                    self.events_processed += 1
                else:
                    self.events_duplicate += 1

                await self.print_stats()

            except Exception as e:
                logger.error(f"Error processing event: {e}")
                logger.error(traceback.format_exc())

    async def print_stats(self):
        current_time = time.time()

        if (
            self.events_processed % self.header_interval == 0
            or current_time - self.last_header_time > 60
        ):
            header = f"{'Time':^12}|{'Processed':^15}|{'Duplicates':^15}"
            logger.debug(header)
            logger.debug("=" * len(header))
            self.last_header_time = current_time

        current_time_str = time.strftime("%H:%M:%S")
        logger.debug(
            f"{current_time_str:^12}|{self.events_processed:^15d}|{self.events_duplicate:^15d}"
        )

    async def handle_msg(self, relay_url: str, message: str):
        logger.debug(f"Received message from {relay_url}: {message}")


async def nostr_client(days_lookback=0):
    signer = Keys.generate()
    pk = signer.public_key()
    logger.info(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()}")

    client = Client(signer)

    for relay in RELAYS:
        logger.info(f"Adding relay: {relay}")
        await client.add_relay(relay)
    await client.connect()

    days_timestamp = Timestamp.from_secs(
        Timestamp.now().as_secs() - (60 * 60 * 24 * days_lookback)
    )

    dvm_filter = Filter().kinds(RELEVANT_KINDS).since(days_timestamp)
    await client.subscribe([dvm_filter])

    notification_handler = NotificationHandler()
    handle_notifications_task = asyncio.create_task(
        client.handle_notifications(notification_handler)
    )

    return client, notification_handler, handle_notifications_task


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime",
        type=int,
        help="Number of minutes to run before exiting",
        default=-1,
    )
    parser.add_argument(
        "--days_lookback",
        type=int,
        help="Number of days in the past to ask relays for events, default is 0",
        default=int(os.getenv("DAYS_LOOKBACK", "1")),
    )
    parser.add_argument(
        "--start-listening",
        action="store_true",
        help="Start listening to relays immediately",
        default=(os.getenv("START_LISTENING", "false").lower() == "true"),
    )
    # historical data arguments
    parser.add_argument(
        "--historical-data",
        action="store_true",
        help="Load events from historical data files instead of connecting to relays",
        default=(os.getenv("LOAD_HISTORICAL_DATA", "false").lower() == "true"),
    )
    parser.add_argument(
        "--historical-data-urls",
        type=str,
        default=os.getenv("HISTORICAL_DATA_URLS", ""),
        help="Optional comma-separated list of specific historical data URLs. If not provided, will automatically discover and sort all available monthly data files.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("HISTORICAL_DATA_BATCH_SIZE", "10000")),
        help="Number of events to process in each batch when loading HISTORICAL data",
    )
    parser.add_argument(
        "--batch-delay",
        type=float,
        default=float(os.getenv("HISTORICAL_DATA_BATCH_DELAY", "0.001")),
        help="Delay in seconds between processing batches of HISTORICAL data",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        help="Maximum number of batches to process (optional)",
    )
    parser.add_argument(
        "--historical-months",
        type=int,
        default=int(os.getenv("HISTORICAL_MONTHS", "0")),
        help="Number of most recent months to process from historical data. If 0 or not set, processes all available months.",
    )
    return parser.parse_args()


async def process_historical_data(args):
    """Process historical data from URLs"""
    logger.info("Starting historical data processing...")
    redis_client = redis.from_url(
        REDIS_URL,
        socket_timeout=5,
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )
    deduplicator = EventDeduplicator(redis_client)

    # Initialize URLs - either from args or discover automatically
    urls = None
    if args.historical_data_urls:
        urls = [url.strip() for url in args.historical_data_urls.split(",") if url.strip()]
        if not urls:
            logger.warning("No valid URLs provided in HISTORICAL_DATA_URLS, will discover automatically")
            urls = await get_historical_data_urls(args.historical_months)
    else:
        logger.info("No URLs provided, will automatically discover and sort available monthly data files")
        urls = await get_historical_data_urls(args.historical_months)

    if not urls:
        logger.error("No historical data URLs found")
        return False

    if args.historical_months:
        logger.info(f"Processing only the most recent {args.historical_months} months of historical data")
    else:
        logger.info("Processing all available historical data")
    
    logger.info(f"Using historical data URLs: {urls}")
    try:
        loader = HistoricalDataLoader(
            redis_client=redis_client,
            urls=urls,
            batch_size=args.batch_size,
            delay_between_batches=args.batch_delay,
            deduplicator=deduplicator,
            max_batches=args.max_batches,
        )
        logger.info("Created historical data loader, now about to run process events parallel")
        await loader.process_events_parallel(max_concurrent=1)
        logger.info("Historical data processing completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error loading historical data: {e}")
        return False

async def listen_to_relays(args):
    """Listen to relays for new events"""
    logger.info("Starting relay listener...")
    reconnect_interval = 240  # Reconnect every 4 minutes
    next_reconnect = time.time() + reconnect_interval

    while True:
        client = None
        handle_notifications_task = None
        try:
            logger.info(f"Connecting to relays (next reconnect at {time.strftime('%H:%M:%S', time.localtime(next_reconnect))})")
            client, notification_handler, handle_notifications_task = await nostr_client(args.days_lookback)

            # Check reconnect time while allowing notifications to process
            try:
                remaining_time = max(0.1, next_reconnect - time.time())
                await asyncio.wait_for(
                    handle_notifications_task,
                    timeout=remaining_time
                )
                logger.info("Notification handler completed naturally, will reconnect...")
            except asyncio.TimeoutError:
                logger.info("Reconnect interval reached, forcing reconnect...")
            except Exception as e:
                logger.error(f"Error in notification handler: {e}")
                logger.error(traceback.format_exc())
            
            # Clean up the current notification handler task
            if handle_notifications_task and not handle_notifications_task.done():
                handle_notifications_task.cancel()
                try:
                    await handle_notifications_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error cancelling notification handler: {e}")

            # Disconnect client and update next reconnect time
            if client:
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting client: {e}")
            
            next_reconnect = time.time() + reconnect_interval
            logger.info(f"Disconnected. Next reconnect at {time.strftime('%H:%M:%S', time.localtime(next_reconnect))}")

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            break
        except Exception as e:
            logger.error(f"Unhandled exception in main: {e}")
            logger.error(traceback.format_exc())
            # Wait before attempting reconnect
            await asyncio.sleep(10)
            # Reset reconnect timer
            next_reconnect = time.time() + reconnect_interval
        finally:
            # Clean up any remaining tasks
            if handle_notifications_task and not handle_notifications_task.done():
                handle_notifications_task.cancel()
                try:
                    await handle_notifications_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error in final task cleanup: {e}")

            if client:
                try:
                    await client.disconnect()
                except Exception as e:
                    logger.error(f"Error in final client cleanup: {e}")


async def main(args):
    """Main entry point with support for historical->relay transition"""
    if args.historical_data:
        logger.info("Historical data mode enabled - will process historical data then switch to relays")
        historical_success = await process_historical_data(args)
        if historical_success:
            logger.info("Historical data processing complete - switching to relay mode")
            if args.start_listening:
                await listen_to_relays(args)
            else:
                logger.info("Not starting relay listener as --start-listening is not enabled")
    else:
        if not args.start_listening:
            logger.info(
                "Not listening to relays. Set START_LISTENING=true to begin or run "
                "`START_LISTENING=true docker compose restart event_collector` after all containers are up."
            )
            while True:
                await asyncio.sleep(3600)  # Sleep for an hour
        else:
            await listen_to_relays(args)

if __name__ == "__main__":
    logger.info("Starting event collector...")
    args = parse_args()

    async def run_program():
        try:
            if args.runtime > 0:
                await asyncio.wait_for(main(args), timeout=(args.runtime * 60))
            else:
                await main(args)
        except FileNotFoundError as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
        except ValueError as e:
            logger.error(f"Invalid configuration: {e}")
            sys.exit(1)
        except asyncio.TimeoutError:
            logger.info(f"Program ran for {args.runtime} minutes and is now exiting.")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            traceback.print_exc()
            sys.exit(1)

    try:
        asyncio.run(run_program())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        logger.info("Program exiting...")
