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
    NostrSigner,
    Kind,
    Event,
)
from celery import Celery
import traceback
import argparse
import datetime
import time
import yaml

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger = loguru.logger
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)
nostr_sdk.init_logger(LogLevel.DEBUG)

# Initialize Celery
celery_app = Celery(
    "event_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0"),
)

RELAYS = os.getenv("RELAYS", "wss://relay.dvmdash.live").split(",")


def load_dvm_config():
    """Load DVM configuration from YAML file. Raises exceptions if file is not found or invalid."""

    # Log the current working directory
    logger.info(f"Current working directory: {os.getcwd()}")

    # List contents of relevant directories
    logger.info("Contents of /app:")
    for item in os.listdir("/app"):
        logger.info(f"  - {item}")

    logger.info("Contents of /app/backend:")
    for item in os.listdir("/app/backend"):
        logger.info(f"  - {item}")

    logger.info("Contents of /app/backend/shared:")
    for item in os.listdir("/app/backend/shared"):
        logger.info(f"  - {item}")

    logger.info("Contents of /app/backend/shared/dvm:")
    for item in os.listdir("/app/backend/shared/dvm"):
        logger.info(f"  - {item}")

    logger.info("Contents of /app/backend/shared/dvm/config:")
    for item in os.listdir("/app/backend/shared/dvm/config"):
        logger.info(f"  - {item}")

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

        logger.info(f"Loaded {len(valid_kinds)} valid kinds")

        return [Kind(k) for k in valid_kinds]
    except Exception as e:
        logger.error(f"Failed to get relevant kinds: {str(e)}")
        raise


# This will now raise an error if the config file can't be found or is invalid
RELEVANT_KINDS = get_relevant_kinds()


class NotificationHandler(HandleNotification):
    def __init__(self):
        self.events_processed = 0
        self.last_header_time = 0
        self.header_interval = 20

    async def print_stats(self):
        current_time = time.time()

        if (
            self.events_processed % self.header_interval == 0
            or current_time - self.last_header_time > 60
        ):
            header = f"{'Time':^12}|{'Events Processed':^20}"
            logger.info(header)
            logger.info("=" * len(header))
            self.last_header_time = current_time
            self.events_processed = 0

        current_time_str = time.strftime("%H:%M:%S")
        logger.info(f"{current_time_str:^12}|{self.events_processed:^20d}")

    async def handle(self, relay_url, subscription_id, event: Event):
        if event.kind() in RELEVANT_KINDS:
            try:
                # Convert the event to a simple dict without any extra wrapping
                event_json = json.loads(event.as_json())

                # Send just the event data directly to Celery
                celery_app.send_task(
                    "celery_worker.src.tasks.process_nostr_event",
                    args=(event_json,),  # Note: single-item tuple needs trailing comma
                    queue="dvmdash",
                )

                self.events_processed += 1
                await self.print_stats()
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                logger.error(traceback.format_exc())

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


async def main(days_lookback=0):
    try:
        client, notification_handler, handle_notifications_task = await nostr_client(
            days_lookback
        )

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


if __name__ == "__main__":
    logger.info("Starting event collector...")
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
    # Add this new argument
    parser.add_argument(
        "--start-listening",
        action="store_true",
        help="Start listening to relays immediately",
        default=(os.getenv("START_LISTENING", "false").lower() == "true"),
    )
    args = parser.parse_args()

    try:
        loop = asyncio.get_event_loop()
        if not args.start_listening:
            logger.info("Not listening to relays. Set START_LISTENING=true to begin.")
            # Just keep the program running without listening
            loop.run_forever()
        elif args.runtime:
            end_time = datetime.datetime.now() + datetime.timedelta(
                minutes=args.runtime
            )
            loop.run_until_complete(
                asyncio.wait_for(main(args.days_lookback), timeout=(args.runtime * 60))
            )
        else:
            loop.run_until_complete(main())
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
