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
import yaml


# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger = loguru.logger
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)
nostr_sdk.init_logger(LogLevel.DEBUG)  # You might want to make this configurable too

# Initialize Celery
celery_app = Celery(
    "event_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0"),
)

RELAYS = os.getenv("RELAYS", "wss://relay.dvmdash.live").split(",")


def load_dvm_config():
    config_path = Path(__file__).parent.parent / "config" / "dvm_kinds.yaml"
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"DVM kinds config not found at {config_path}, using defaults")


def get_relevant_kinds():
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
    excluded_kinds = {k["kind"] for k in config["excluded_kinds"]}

    # Combine all kinds
    all_kinds = set(known_kinds + list(request_range) + list(result_range))

    # Remove excluded kinds
    valid_kinds = all_kinds - excluded_kinds

    return [Kind(k) for k in valid_kinds]


RELEVANT_KINDS = get_relevant_kinds()


class NotificationHandler(HandleNotification):
    def __init__(self, max_batch_size=100, max_wait_time=3):
        self.event_queue = asyncio.Queue()
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.row_count = 0
        self.last_header_time = 0
        self.header_interval = 20

    async def print_queue_sizes(self):
        current_time = time.time()
        event_queue_size = self.event_queue.qsize()

        if (
            self.row_count % self.header_interval == 0
            or current_time - self.last_header_time > 60
        ):
            header = f"{'Time':^12}|{'Event Queue':^15}"
            LOGGER.info(header)
            LOGGER.info("=" * len(header))
            self.last_header_time = current_time
            self.row_count = 0

        current_time_str = time.strftime("%H:%M:%S")
        LOGGER.info(f"{current_time_str:^12}|{event_queue_size:^15d}")
        self.row_count += 1

    async def handle(self, relay_url, subscription_id, event: Event):
        if event.kind() in RELEVANT_KINDS:
            event_json = json.loads(event.as_json())
            await self.event_queue.put(event_json)
        await self.print_queue_sizes()

    async def process_events(self):
        while True:
            try:
                batch = []
                try:
                    # Wait for the first event or until max_wait_time
                    event = await asyncio.wait_for(
                        self.event_queue.get(), timeout=self.max_wait_time
                    )
                    batch.append(event)

                    # Collect more events if available, up to max_batch_size
                    while (
                        len(batch) < self.max_batch_size
                        and not self.event_queue.empty()
                    ):
                        batch.append(self.event_queue.get_nowait())

                except asyncio.TimeoutError:
                    continue

                if batch:
                    # Send batch to Celery for processing
                    celery_app.send_task("tasks.process_event_batch", args=[batch])
                    LOGGER.info(f"Sent batch of {len(batch)} events to Celery")

                # Mark tasks as done
                for _ in range(len(batch)):
                    self.event_queue.task_done()

            except Exception as e:
                LOGGER.error(f"Unhandled exception in process_events: {e}")
                LOGGER.error(traceback.format_exc())
                await asyncio.sleep(5)


async def nostr_client(days_lookback=0):
    keys = Keys.generate()
    pk = keys.public_key()
    LOGGER.info(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()}")

    signer = NostrSigner.keys(keys)
    client = Client(signer)

    for relay in RELAYS:
        await client.add_relay(relay)
    await client.connect()

    days_timestamp = Timestamp.from_secs(
        Timestamp.now().as_secs() - (60 * 60 * 24 * days_lookback)
    )

    dvm_filter = Filter().kinds(RELEVANT_KINDS).since(days_timestamp)
    await client.subscribe([dvm_filter])

    notification_handler = NotificationHandler()

    # Create tasks
    process_events_task = asyncio.create_task(notification_handler.process_events())
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
        LOGGER.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        LOGGER.error(f"Unhandled exception in main: {e}")
        traceback.print_exc()
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            LOGGER.error(f"Error disconnecting client: {e}")

        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()

        await asyncio.gather(*asyncio.all_tasks(), return_exceptions=True)
        LOGGER.info("All tasks have been cancelled, exiting...")


if __name__ == "__main__":
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
        default=0,
    )
    args = parser.parse_args()

    loop = asyncio.get_event_loop()

    try:
        if args.runtime:
            end_time = datetime.datetime.now() + datetime.timedelta(
                minutes=args.runtime
            )
            loop.run_until_complete(
                asyncio.wait_for(main(args.days_lookback), timeout=(args.runtime * 60))
            )
        else:
            loop.run_until_complete(main())
    except asyncio.TimeoutError:
        LOGGER.info(f"Program ran for {args.runtime} minutes and is now exiting.")
    except Exception as e:
        LOGGER.error(f"Fatal error in main loop: {e}")
        traceback.print_exc()
    finally:
        loop.close()
        LOGGER.info("Event loop closed, exiting...")
