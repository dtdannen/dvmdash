import asyncio
import random
import sys
from datetime import datetime, timedelta
import nostr_sdk
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
from neo4j import AsyncGraphDatabase
import motor.motor_asyncio
import pymongo  # used only to create new collections if they don't exist
from pymongo.errors import BulkWriteError
from general.dvm import EventKind


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

    # connect to db synchronously
    sync_mongo_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
    sync_db = sync_mongo_client["dvmdash"]

    # connect to async db
    async_mongo_client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGO_URI"))
    async_db = async_mongo_client["dvmdash"]

    try:
        result = async_db["events"].count_documents({})
        LOGGER.info(f"There are {result} documents in events collection")
    except Exception as e:
        LOGGER.error("Could not count documents in async_db")
        import traceback

        traceback.print_exc()

    LOGGER.info("Connected to cloud mongo async_db")

    if os.getenv("USE_LOCAL_NEO4J", "False") != "False":
        # use local
        URI = os.getenv("NEO4J_LOCAL_URI")
        AUTH = (os.getenv("NEO4J_LOCAL_USERNAME"), os.getenv("NEO4J_LOCAL_PASSWORD"))

        neo4j_driver = AsyncGraphDatabase.driver(
            URI,
            auth=AUTH,
            # encrypted=True,
            # trust=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES,
        )

        neo4j_driver.verify_connectivity()
        LOGGER.info("Verified connectivity to local Neo4j")
    else:
        URI = os.getenv("NEO4J_URI")
        AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))

        neo4j_driver = AsyncGraphDatabase.driver(
            URI,
            auth=AUTH,
            # encrypted=True,
            # trust=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES,
        )

        neo4j_driver.verify_connectivity()
        LOGGER.info("Verified connectivity to cloud Neo4j")

    return sync_db, async_db, neo4j_driver


SYNC_MONGO_DB, ASYNC_MONGO_DB, NEO4J_DRIVER = setup_database()


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
                EventKind.DVM_REQUEST_RANGE_START.value,
                EventKind.DVM_REQUEST_RANGE_END.value,
            )
        )
        + list(
            range(
                EventKind.DVM_RESULT_RANGE_START.value,
                EventKind.DVM_RESULT_RANGE_END.value,
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
            result = SYNC_MONGO_DB["events"].insert_many(events, ordered=False)
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


def old_main():
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


def create_test_events_collection():
    # create the index if it doesn't exist already
    collection_name = "test_events"
    if collection_name not in SYNC_MONGO_DB.list_collection_names():
        SYNC_MONGO_DB.create_collection(collection_name)


def new_async_main():
    LOGGER.info("Starting async listen for events script")
    create_test_events_collection()
    # count the number of events in the mongo db
    docs = []

    async def get_some_docs():
        cursor = ASYNC_MONGO_DB.events.find({})
        # Modify the query before iterating
        cursor.limit(5)
        async for document in cursor:
            docs.append(document)
        return docs

    async def write_test_docs():
        result = await ASYNC_MONGO_DB.test_events.insert_many(docs, ordered=False)
        LOGGER.info("inserted %d docs" % (len(result.inserted_ids),))

    async def create_test_nodes_in_neo4j():
        query = """
        MERGE (n:TestEvent {id: $event_id})
        ON CREATE SET n += apoc.convert.fromJsonMap($json)
        ON MATCH SET n += apoc.convert.fromJsonMap($json)
        RETURN n
        """

        async with NEO4J_DRIVER.session() as session:
            for doc in docs:
                event_id = str(doc.get("id"))  # Assuming 'id' is the unique identifier
                doc_copy = doc.copy()  # Create a copy of the document
                doc_copy.pop("_id", None)  # Remove '_id' from the copy if it exists
                doc_copy.pop("tags", None)
                json_data = json.dumps(
                    doc_copy
                )  # Convert the modified document to a JSON string

                try:
                    result = await session.run(query, event_id=event_id, json=json_data)
                    summary = await result.consume()
                    LOGGER.info(
                        f"Created/Updated node for event {event_id}. "
                        f"Nodes created: {summary.counters.nodes_created}, "
                        f"Properties set: {summary.counters.properties_set}"
                    )
                except Exception as e:
                    LOGGER.error(
                        f"Error creating/updating node for event {event_id}: {str(e)}"
                    )

        LOGGER.info("Finished creating test nodes in Neo4j")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_some_docs())

    LOGGER.info(f"docs now has length {len(docs)}")
    for doc in docs:
        LOGGER.info(f"doc is {doc}")

    loop.run_until_complete(create_test_nodes_in_neo4j())

    LOGGER.info(f"after neo4j, docs now has length {len(docs)}")

    loop.run_until_complete(write_test_docs())


if __name__ == "__main__":
    new_async_main()
