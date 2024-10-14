import random
import sys
from datetime import datetime, timedelta
import nostr_sdk
import pymongo
from pymongo import MongoClient
import json
import os
import time
from pathlib import Path
from threading import Thread, Lock
import ctypes
import loguru
import dotenv
from nostr_sdk import (
    Keys,
    Client,
    Tag,
    EventBuilder,
    Filter,
    HandleNotification,
    Timestamp,
    nip04_decrypt,
    LogLevel,
    NostrSigner,
    Kind,
    SubscribeAutoCloseOptions,
    Options,
    Event,
)
from pymongo.errors import BulkWriteError
from shared.dvm import EventKind


def setup_logging():
    # Create a logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Configure the logger to use the DEBUG level
    loguru.logger.remove()  # Remove the default logger
    loguru.logger.add(sys.stderr, level="DEBUG")

    # Init nostr_sdk logger
    nostr_sdk.init_logger(LogLevel.DEBUG)

    return loguru.logger


# set up logging

LOGGER = setup_logging()
LOGGER.info("Starting up in current directory: ", os.getcwd())


def setup_environment():
    env_path = Path(".env")
    if env_path.is_file():
        LOGGER.info(f"Loading environment from {env_path.resolve()}")
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        LOGGER.error(f".env file not found at {env_path} ")
        raise FileNotFoundError(f".env file not found at {env_path} ")


setup_environment()


def setup_database():
    LOGGER.debug("os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False))

    if (
        os.getenv("USE_MONGITA", "False") != "False"
    ):  # use a local mongo db, like sqlite
        LOGGER.debug(
            "os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False)
        )
        LOGGER.info("Using mongita")
        from mongita import MongitaClientDisk

        mongo_client = MongitaClientDisk()
        db = mongo_client.dvmdash
        LOGGER.info("Connected to local mongo db using MONGITA")
    else:
        # connect to db
        mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True)
        db = mongo_client["dvmdash"]

        try:
            result = db["events"].count_documents({})
            LOGGER.info(f"There are {result} documents in events collection")
        except Exception as e:
            LOGGER.error("Could not count documents in db")
            import traceback

            traceback.print_exc()

        LOGGER.info("Connected to cloud mongo db")

    return db


DB = setup_database()


def get_relays():
    relays = os.getenv(
        "RELAYS",
        "wss://relay.damus.io,wss://blastr.f7z.xyz,wss://relayable.org,wss://nostr-pub.wellorder.net",
    ).split(",")
    return relays


RELAYS = get_relays()


def get_relevant_kinds():
    # Kinds to listen to
    known_kinds = [
        EventKind.DM.value,
        EventKind.ZAP.value,
        EventKind.DVM_NIP89_ANNOUNCEMENT.value,
        EventKind.DVM_FEEDBACK.value,
    ]

    all_kinds = set(
        known_kinds
        + list(
            range(
                EventKind.DVM_RANGE_START.value,
                EventKind.DVM_RANGE_END.value,
            )
        )
        + list(
            range(
                EventKind.DVM_FEEDBACK_RANGE_START.value,
                EventKind.DVM_FEEDBACK_RANGE_END.value,
            )
        )
    )

    relevant_kinds = [
        Kind(k) for k in list(all_kinds - set(EventKind.get_bad_dvm_kinds()))
    ]
    return relevant_kinds


# ugly, but we want it to be global, and only set once
RELEVANT_KINDS = get_relevant_kinds()


def write_events_to_db(events):
    if events:
        try:
            result = DB["events"].insert_many(events, ordered=False)
            LOGGER.info(
                f"Finished writing events to db with result: {len(result.inserted_ids)}"
            )
        except BulkWriteError as e:
            # If you want to log the details of the duplicates or other errors
            num_duplicates_found = len(e.details["writeErrors"])
            LOGGER.warning(
                f"Ignoring {num_duplicates_found} / {len(events)} duplicate events...",
                end="",
            )
        except Exception as e:
            LOGGER.error(f"Error inserting events into database: {e}")


class NotificationHandler(HandleNotification):
    def __init__(self):
        self.events = []
        self.lock = Lock()
        self.flush_interval = 10  # Flush every 10 seconds, adjust as needed
        self.stop_requested = False  # Flag to signal thread to stop

        # Start a thread to flush events periodically
        self.flush_thread = Thread(target=self.flush_events_periodically)
        self.flush_thread.start()

    def handle(self, relay_url, subscription_id, event: Event):
        if event.kind() in RELEVANT_KINDS:
            with self.lock:
                self.events.append(json.loads(event.as_json()))

    def flush_events(self):
        with self.lock:
            if self.events:
                LOGGER.debug("locking to write to db...", end="")
                LOGGER.debug(f"...writing {len(self.events)} to db...", end="")
                write_events_to_db(self.events)
                self.events.clear()
                LOGGER.debug("...unlocking write to db")

    def flush_events_periodically(self):
        while not self.stop_requested:
            time.sleep(self.flush_interval)
            self.flush_events()

    def request_stop(self):
        self.stop_requested = True

    def handle_msg(self, relay_url, msg):
        return


def nostr_client(since_when_timestamp: Timestamp, runtime_limit: Timestamp):
    keys = Keys.generate()
    pk = keys.public_key()
    LOGGER.info(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()} ")
    signer = NostrSigner.keys(keys)
    client = Client(signer)
    for relay in RELAYS:
        client.add_relay(relay)
    client.connect()

    dvm_filter = Filter().kinds(RELEVANT_KINDS).since(since_when_timestamp)
    client.subscribe([dvm_filter], None)

    handler = NotificationHandler()
    client.handle_notifications(handler)

    while Timestamp.now().as_secs() < runtime_limit.as_secs():
        LOGGER.debug(
            f"There are this many seconds left: {runtime_limit.as_secs() - Timestamp.now().as_secs()}"
        )
        delay = 10
        LOGGER.debug(f"About to sleep for {delay} seconds...", end="")
        time.sleep(delay)
        LOGGER.debug(f"waking up...")

    LOGGER.info("Time is up. Requesting stop.")
    client.disconnect()
    handler.request_stop()


def run_nostr_client(run_time_limit_minutes=10, look_back_minutes=120):
    current_timestamp = Timestamp.now()
    current_secs = current_timestamp.as_secs()

    max_run_time = Timestamp.from_secs(current_secs + int(run_time_limit_minutes * 60))
    look_back_time = Timestamp.from_secs(current_secs - int(look_back_minutes * 60))

    env_path = Path(".env")
    if env_path.is_file():
        LOGGER.info(f"loading environment from {env_path.resolve()}")
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        LOGGER.error(f".env file not found at {env_path} ")
        raise FileNotFoundError(f".env file not found at {env_path} ")

    nostr_dvm_thread = Thread(target=nostr_client, args=(look_back_time, max_run_time))
    nostr_dvm_thread.start()
    nostr_dvm_thread.join()  # Wait for the thread to finish


if __name__ == "__main__":
    # get the limits from sys.args
    if len(sys.argv) == 4:
        RUNTIME_LIMIT = int(sys.argv[1])
        LOOKBACK_TIME = int(sys.argv[2])
        WAIT_LIMIT = int(sys.argv[3])
    else:
        print(
            "Usage: python listen_for_DVM_events.py <RUNTIME_LIMIT_AS_MINS>"
            " <LOOKBACK_TIME_AS_MINS> <WAIT_LIMIT_AS_SECS>\n"
            "Example: python listen_for_DVM_events.py 10 120 60\n"
        )
        sys.exit(1)

    try:
        LOGGER.info(f"Starting client run with RUNTIME_LIMIT: {RUNTIME_LIMIT} minutes")
        LOGGER.info(f"Starting client run with LOOKBACK_TIME: {LOOKBACK_TIME} minutes")
        LOGGER.info(f"Starting client run with WAIT_LIMIT: {WAIT_LIMIT} seconds")

        run_nostr_client(
            RUNTIME_LIMIT, LOOKBACK_TIME
        )  # Replace 3 with your desired run time limit in minutes
        LOGGER.info(
            f"Client run completed. Sleeping for {WAIT_LIMIT} seconds before exiting completely"
        )
        time.sleep(WAIT_LIMIT)  # Sleep for a short time before restarting
        LOGGER.info("Goodbye!")
    except Exception as e:
        LOGGER.error(f"Exception occurred: {e}")
        LOGGER.info(
            f"Client exception occurred. Sleeping for {WAIT_LIMIT} seconds before exiting completely"
        )
        time.sleep(
            WAIT_LIMIT
        )  # Sleep for a short time before restarting in case of an exception
        LOGGER.info("Goodbye!")
