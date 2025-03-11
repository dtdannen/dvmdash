import asyncio
import json
import os
import re
from pathlib import Path
import tempfile
import aiohttp
import redis
import time
import logging
from typing import Optional, List, Dict, AsyncIterator
from redis import Redis

logger = logging.getLogger(__name__)

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

async def get_historical_data_urls(historical_months: Optional[int] = None) -> List[str]:
    """
    Get historical data files from CDN, sorted by date.
    If historical_months is set, returns only the most recent X months of data.
    """
    base_url = 'https://dvmdashbucket.nyc3.cdn.digitaloceanspaces.com'
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
                    async with session.head(url) as response:
                        if response.status == 200:
                            files.append(filename)
                except Exception:
                    continue
    
    # Sort files by date
    def sort_key(filename):
        try:
            year, month = parse_filename_date(filename)
            return year * 100 + month
        except ValueError:
            return float('inf')
            
    sorted_files = sorted(files, key=sort_key, reverse=True)
    
    if historical_months is not None and historical_months > 0:
        sorted_files = sorted_files[:historical_months]
        
    sorted_files.sort(key=sort_key)
    
    return [f'{base_url}/{filename}' for filename in sorted_files]

class HistoricalDataLoader:
    """
    Loads historical data from JSON files and feeds events to Redis queue in batches.
    Uses streaming to handle large files efficiently.
    """

    def __init__(
        self,
        redis_client: Redis,
        urls: Optional[List[str]] = None,
        batch_size: int = 10000,
        delay_between_batches: float = 0.05,
        deduplicator=None,
        max_batches: Optional[int] = None,
        relevant_kinds: Optional[List[int]] = None
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
        self.relevant_kinds = set(relevant_kinds) if relevant_kinds else None

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

        raise Exception(f"Failed to download file from {url} after {max_retries} attempts")

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
            logger.info(f"Starting to process events from {url}")
            temp_path = None

            try:
                temp_path = await self.download_file(url)
                async for batch in self._read_batches(temp_path):
                    batch_duplicates = 0
                    batch_processed = 0

                    for event in batch:
                        if self.relevant_kinds is None or int(event["kind"]) in self.relevant_kinds:
                            is_duplicate = False
                            if self.deduplicator:
                                is_duplicate = self.deduplicator.check_duplicate(event["id"])

                            if not is_duplicate:
                                self.redis.rpush("dvmdash_events", json.dumps(event))
                                batch_processed += 1
                            else:
                                batch_duplicates += 1

                    self.events_processed += batch_processed
                    self.events_duplicate += batch_duplicates
                    self.batches_processed += 1

                    await self._print_stats()
                    await asyncio.sleep(self.delay_between_batches)

                    if self.max_batches and self.batches_processed >= self.max_batches:
                        logger.info(f"\nReached maximum batch limit of {self.max_batches}")
                        return

                logger.info(f"Completed processing events from {url}")

            except Exception as e:
                logger.error(f"Error processing URL {url}: {e}")
                raise
            finally:
                if temp_path and temp_path.exists():
                    try:
                        os.unlink(temp_path)
                    except Exception as e:
                        logger.error(f"Error cleaning up temp file {temp_path}: {e}")

    async def _read_batches(self, filepath: Path) -> AsyncIterator[List[Dict]]:
        """Read JSON file in batches using ijson for memory efficiency."""
        try:
            import ijson

            logger.info("Starting streaming JSON processing...")
            current_batch = []

            with open(filepath, "rb") as f:
                parser = ijson.items(f, "item")

                for event in parser:
                    current_batch.append(event)

                    if len(current_batch) >= self.batch_size:
                        yield current_batch
                        current_batch = []

                        if self.max_batches and self.batches_processed + 1 >= self.max_batches:
                            break

            if current_batch and (not self.max_batches or self.batches_processed < self.max_batches):
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

        if (self.events_processed % self.header_interval == 0 or 
            current_time - self.last_header_time > 10):
            header = f"{'Time':^12}|{'Processed':^15}|{'Duplicates':^15}|{'Batches':^10}"
            logger.info(header)
            logger.info("=" * len(header))
            self.last_header_time = current_time

        current_time_str = time.strftime("%H:%M:%S")
        logger.info(
            f"{current_time_str:^12}|{self.events_processed:^15d}|"
            f"{self.events_duplicate:^15d}|{self.batches_processed:^10d}"
        )

async def process_historical_data(redis_url: str, args, relevant_kinds: Optional[List[int]] = None) -> bool:
    """Process historical data from URLs"""
    logger.info("Starting historical data processing...")
    redis_client = redis.from_url(
        redis_url,
        socket_timeout=5,
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )

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
            max_batches=args.max_batches,
            relevant_kinds=relevant_kinds
        )
        await loader.process_events()
        logger.info("Historical data processing completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error loading historical data: {e}")
        return False
