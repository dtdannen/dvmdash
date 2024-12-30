import asyncio
import sys
import nostr_sdk
import json
import os
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
from redis import Redis
from typing import Optional, Tuple, AsyncIterator, Dict

# print all the env variables to the console, to see what we start with:
print("Environment variables:")
for key, value in os.environ.items():
    print(f"{key}={value}")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger = loguru.logger
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)
nostr_sdk.init_logger(LogLevel.DEBUG)


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


def get_relevant_kinds():
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


class TestDataLoader:
    """
    Loads test data from a MongoDB JSON export file and simulates real-time event ingestion
    by feeding events to Redis queue in batches. Uses streaming to handle large files efficiently.
    """

    def __init__(
        self,
        redis_client,
        filepath: str,
        batch_size: int = 10000,
        delay_between_batches: float = 0.05,
        deduplicator=None,
        max_batches: Optional[int] = None,
    ):
        self.redis = redis_client
        self.filepath = Path(filepath)
        self.batch_size = batch_size
        self.delay_between_batches = delay_between_batches
        self.deduplicator = deduplicator
        self.max_batches = max_batches
        self.events_processed = 0
        self.events_duplicate = 0
        self.batches_processed = 0
        self.last_header_time = 0
        self.header_interval = 20

    async def process_events(self) -> None:
        """Process events from file in batches."""
        try:
            async for batch in self._read_batches():
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
                    logger.info(f"\nReached maximum batch limit of {self.max_batches}")
                    break

        except Exception as e:
            logger.error(f"Error processing test data: {e}")
            raise

    async def _read_batches(self) -> AsyncIterator[list[Dict]]:
        """Read MongoDB export JSON file in batches using ijson for memory efficiency."""
        try:
            import ijson  # Import here to keep it optional

            logger.info("Starting streaming JSON processing...")
            current_batch = []

            with open(self.filepath, "rb") as f:  # Open in binary mode for ijson
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
            logger.info(header)
            logger.info("=" * len(header))
            self.last_header_time = current_time

        current_time_str = time.strftime("%H:%M:%S")
        logger.info(
            f"{current_time_str:^12}|{self.events_processed:^15d}|"
            f"{self.events_duplicate:^15d}|{self.batches_processed:^10d}"
        )


async def load_test_data(
    redis_client,
    filepath: str,
    batch_size: int = 10000,
    delay: float = 0.05,
    deduplicator=None,
    max_batches: Optional[int] = None,
) -> None:
    """Helper function to load test data."""
    loader = TestDataLoader(
        redis_client=redis_client,
        filepath=filepath,
        batch_size=batch_size,
        delay_between_batches=delay,
        deduplicator=deduplicator,
        max_batches=max_batches,
    )
    await loader.process_events()


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
            logger.info(
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
                        logger.info(
                            f"Cleanup triggered. Removed {removed:,} events. New size: {new_size:,}"
                        )

                return not is_new

        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False


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
            logger.info(header)
            logger.info("=" * len(header))
            self.last_header_time = current_time

        current_time_str = time.strftime("%H:%M:%S")
        logger.info(
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
        help="Number of minutes to run before exiting, default is 360 (6 hrs)",
        default=360,
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
    # Test data arguments
    parser.add_argument(
        "--test-data",
        action="store_true",
        help="Load events from test data file instead of connecting to relays",
    )
    parser.add_argument(
        "--test-data-path",
        type=str,
        default="backend/event_collector/test_data/dvmdash.prod_events_29NOV2024.json",
        help="Path to test data JSON file",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of events to process in each batch when loading test data",
    )
    parser.add_argument(
        "--batch-delay",
        type=float,
        default=0.001,
        help="Delay in seconds between processing batches of test data",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        help="Maximum number of batches to process (optional)",
    )
    return parser.parse_args()


async def main(args):
    if args.test_data:
        # Initialize Redis and deduplicator
        redis_client = redis.from_url(REDIS_URL)
        deduplicator = EventDeduplicator(redis_client)

        logger.info(f"Loading test data from {args.test_data_path}")
        try:
            await load_test_data(
                redis_client=redis_client,
                filepath=args.test_data_path,
                batch_size=args.batch_size,
                delay=args.batch_delay,
                deduplicator=deduplicator,
                max_batches=args.max_batches,
            )
        except FileNotFoundError:
            logger.error(f"Test data file not found: {args.test_data_path}")
            return
        except Exception as e:
            logger.error(f"Error loading test data: {e}")
            return
    else:
        try:
            (
                client,
                notification_handler,
                handle_notifications_task,
            ) = await nostr_client(args.days_lookback)

            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        except Exception as e:
            logger.error(f"Unhandled exception in main: {e}")
            traceback.print_exc()
        finally:
            try:
                await client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client: {e}")

            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()

            await asyncio.gather(*asyncio.all_tasks(), return_exceptions=True)
            logger.info("All tasks have been cancelled, exiting...")


# Update your __main__ section:
if __name__ == "__main__":
    logger.info("Starting event collector...")
    args = parse_args()

    try:
        loop = asyncio.get_event_loop()
        if args.test_data:
            # Run test data loader
            loop.run_until_complete(main(args))
        elif not args.start_listening:
            logger.info(
                "Not listening to relays. Set START_LISTENING=true to begin or run "
                "`START_LISTENING=true docker compose restart event_collector` after all containers are up."
            )
            loop.run_forever()
        elif args.runtime:
            end_time = datetime.datetime.now() + datetime.timedelta(
                minutes=args.runtime
            )
            loop.run_until_complete(
                asyncio.wait_for(main(args), timeout=(args.runtime * 60))
            )
        else:
            loop.run_until_complete(main(args))
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Invalid configuration: {e}")
        sys.exit(1)
    except asyncio.TimeoutError:
        logger.info(f"Program ran for {args.runtime} minutes and is now exiting.")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        loop.close()
        logger.info("Event loop closed, exiting...")
