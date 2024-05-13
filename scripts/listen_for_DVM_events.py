import sys

import nostr_sdk
import pymongo
from pymongo import MongoClient
import json
import os
import time
from pathlib import Path
from threading import Thread
import ctypes
from datetime import datetime, timedelta

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
import logging
from general.dvm import EventKind

logger = loguru.logger

# init logger
nostr_sdk.init_logger(LogLevel.DEBUG)

env_path = Path(".env")
if env_path.is_file():
    logger.info(f"loading environment from {env_path.resolve()}")
    dotenv.load_dotenv(env_path, verbose=True, override=True)
else:
    logger.error(f".env file not found at {env_path} ")
    raise FileNotFoundError(f".env file not found at {env_path} ")

logger.debug("os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False))

if os.getenv("USE_MONGITA", "False") != "False":  # use a local mongo db, like sqlite
    logger.debug("os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False))
    logger.info("Using mongita")
    from mongita import MongitaClientDisk

    mongo_client = MongitaClientDisk()
    db = mongo_client.dvmdash
    logger.info("Connected to local mongo db using MONGITA")
else:
    # connect to db
    mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True)
    db = mongo_client["dvmdash"]

    try:
        result = db["events"].count_documents({})
        logger.info(f"There are {result} documents in events collection")
    except Exception as e:
        logger.error("Could not count documents in db")
        import traceback

        traceback.print_exc()

    logger.info("Connected to cloud mongo db")


RELAYS = os.getenv(
    "RELAYS",
    "wss://relay.damus.io,wss://blastr.f7z.xyz,wss://relayable.org,wss://nostr-pub.wellorder.net",
).split(",")

logger.info(f"Listening to {len(RELAYS)} RELAYS:\n\t{RELAYS}")

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

RELEVANT_KINDS = [Kind(k) for k in list(all_kinds - set(EventKind.get_bad_dvm_kinds()))]

# DVM_KINDS = [31990]


SCRIPT_START_TIME = datetime.now()


def write_events_to_db(events):
    if events:
        try:
            result = db["events"].insert_many(events, ordered=False)
            logger.info(
                f"Finished writing events to db with result: {len(result.inserted_ids)}"
            )
        except BulkWriteError as e:
            # If you want to log the details of the duplicates or other errors
            num_duplicates_found = len(e.details["writeErrors"])
            logger.warning(
                f"Ignoring {num_duplicates_found} / {len(events)} duplicate events...",
                end="",
            )
        except Exception as e:
            logger.error(f"Error inserting events into database: {e}")


import threading
import time
from threading import Lock


class NotificationHandler(HandleNotification):
    def __init__(self):
        self.events = []
        self.lock = Lock()
        self.flush_interval = 10  # Flush every 10 seconds, adjust as needed
        self.stop_requested = False  # Flag to signal thread to stop

        # Start a thread to flush events periodically
        self.flush_thread = threading.Thread(target=self.flush_events_periodically)
        self.flush_thread.start()

    def handle(self, relay_url, subscription_id, event: Event):
        # print(f"Received new event from {relay_url}: {event.as_json()}")
        if event.kind() in RELEVANT_KINDS:  # try catching new DVMs
            with self.lock:
                # print("locking to append to events")
                self.events.append(json.loads(event.as_json()))
                # print("unlocking to append to events")

    def flush_events(self):
        with self.lock:
            if self.events:
                logger.debug("locking to write to db...", end="")
                logger.debug(f"...writing {len(self.events)} to db...", end="")
                write_events_to_db(
                    self.events
                )  # Assuming this function writes a list of events to the DB
                self.events.clear()
                logger.debug("...unlocking write to db")

    def flush_events_periodically(self):
        while not self.stop_requested:
            time.sleep(self.flush_interval)
            self.flush_events()

    def request_stop(self):
        self.stop_requested = True

    def handle_msg(self, relay_url, msg):
        return


# The rest of your code remains the same

# Make sure to handle graceful shutdown of the flush thread when your application exits


def nostr_client(since_when_timestamp):
    keys = Keys.parse(os.environ.get("DVM_PRIVATE_KEY_TEST_CLIENT", None))
    sk = keys.secret_key()
    pk = keys.public_key()
    logger.info(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()} ")
    signer = NostrSigner.keys(keys)
    client = Client(signer)
    for relay in RELAYS:
        client.add_relay(relay)
    client.connect()

    # dm_zap_filter = Filter().kinds([EventDefinitions.KIND_DM,
    #                                EventDefinitions.KIND_ZAP]).since(since_when_timestamp)

    # opts = (
    #     Options()
    #     .connection_timeout(timedelta(seconds=60))
    #     .send_timeout(timedelta(seconds=10))
    # )
    # options.auto_close = False

    # events to us specific
    dvm_filter = Filter().kinds(RELEVANT_KINDS).since(since_when_timestamp)
    # public events
    client.subscribe([dvm_filter], None)
    # client.subscribe([dvm_filter])

    client.handle_notifications(NotificationHandler())
    while True:
        delay = 10
        logger.debug(f"About to sleep for {delay} seconds...", end="")
        time.sleep(delay)
        logger.debug(f"waking up...")


def run_nostr_client(minutes=10080):
    current_timestamp = Timestamp.now()
    current_secs = current_timestamp.as_secs()

    max_time = Timestamp.from_secs(current_secs - int(minutes * 60))

    env_path = Path(".env")
    if env_path.is_file():
        logger.info(f"loading environment from {env_path.resolve()}")
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        logger.error(f".env file not found at {env_path} ")
        raise FileNotFoundError(f".env file not found at {env_path} ")

    nostr_dvm_thread = Thread(target=nostr_client, args=(max_time,))
    nostr_dvm_thread.start()


if __name__ == "__main__":
    ### TEST CODE TO PUT AN EVENT INTO PYMONGO
    # test_event_1 = {
    #     "id": "test1",
    #     "pubkey": "c63c5b4e21b9b1ec6b73ad0449a6a8589f6bd8542cabd9e5de6ae474b28fe806",
    #     "created_at": 1705189941,
    #     "kind": 5100,
    #     "tags": [
    #         ["p", "89669b03bb25232f33192fdda77b8e36e3d3886e9b55b3c74b95091e916c8f98"],
    #         ["encrypted"],
    #     ],
    #     "content": "k84/yUywhNvWhDUOhxC/dWIb+w5R6KybLl0BpykYcDqY0ky7sJC4rnbxfsKvMjh1zIexyQ75M+NRxqA/JnBEekPw93xu6TfqtH/tVThbyOWG0fn77ptM1aEPziI52kwbM0hrSbtsJxKEm9LfWvF7+s9yv4/pqIkYMiMZ56JqxG/XH+3DxXoa0ZJQr1GRBpfsb1h8WMA5EqmEOB/OSKyeA9J7/7/U4ONHcsBc0yTPCBJ6pnTlgF19scwAvGXw9F1sG9gc/65nzvsfjaQ4venFh0A9QpH9f4/02qyBnOTcmTs0RIT9etyEZQeBoJlJL9+Tu1OD6sp66hbZ6GDVWzOtvz1Us+Wsv3fWBz0rDKQLnWCEj5BIfEkjZJcmJY+GLmNrTKnxsCZ/HmUqMUMolm4Q8SWmNK1TtMZ6Nmw6tEP45zkWpSXxznY2mSl4Ipa8vj+DuT+id319Twwq28Qhc0jdj4rMRdV5OwDQfyqUFAK0kFSzNqJ72ntn6/HLfJBtKVHoRqB7xB+u4M7n8o/9LS4DLmSjk8tSOcvqvCSa+0CDqkFdQh+bm5wttAX4bpFv5Zyrj9HIImfvmfJZgDXm43PUeqz9FjtRlalh7dJfVwlwsE+MTq553sSkKSGYK1j4pwKB3JDwMiJP8m8AzoijZRhyFvqYFX4yw5Ykrftg2OHPJ16FUoMOlL4p6+cEgm+yUOKC+az++PhTjOuHJMHPAg+XkA==?iv=M2Vvnlu6pJcf6if1x7ef7g==",
    #     "sig": "2e8eaef67f40796be09be5a77b0ea7707e496484355774c13c078fbda4adb172301308dfc6d6256a2d65c33e5716dfd8efb1e6704cf5457ee723901ca1c7534c",
    # }
    #
    # test_event_3 = {
    #     "id": "test4",
    #     "pubkey": "c63c5b4e21b9b1ec6b73ad0449a6a8589f6bd8542cabd9e5de6ae474b28fe806",
    #     "created_at": 1705189941,
    #     "kind": 5100,
    #     "tags": [
    #         ["p", "89669b03bb25232f33192fdda77b8e36e3d3886e9b55b3c74b95091e916c8f98"],
    #         ["encrypted"],
    #     ],
    #     "content": "k84/yUywhNvWhDUOhxC/dWIb+w5R6KybLl0BpykYcDqY0ky7sJC4rnbxfsKvMjh1zIexyQ75M+NRxqA/JnBEekPw93xu6TfqtH/tVThbyOWG0fn77ptM1aEPziI52kwbM0hrSbtsJxKEm9LfWvF7+s9yv4/pqIkYMiMZ56JqxG/XH+3DxXoa0ZJQr1GRBpfsb1h8WMA5EqmEOB/OSKyeA9J7/7/U4ONHcsBc0yTPCBJ6pnTlgF19scwAvGXw9F1sG9gc/65nzvsfjaQ4venFh0A9QpH9f4/02qyBnOTcmTs0RIT9etyEZQeBoJlJL9+Tu1OD6sp66hbZ6GDVWzOtvz1Us+Wsv3fWBz0rDKQLnWCEj5BIfEkjZJcmJY+GLmNrTKnxsCZ/HmUqMUMolm4Q8SWmNK1TtMZ6Nmw6tEP45zkWpSXxznY2mSl4Ipa8vj+DuT+id319Twwq28Qhc0jdj4rMRdV5OwDQfyqUFAK0kFSzNqJ72ntn6/HLfJBtKVHoRqB7xB+u4M7n8o/9LS4DLmSjk8tSOcvqvCSa+0CDqkFdQh+bm5wttAX4bpFv5Zyrj9HIImfvmfJZgDXm43PUeqz9FjtRlalh7dJfVwlwsE+MTq553sSkKSGYK1j4pwKB3JDwMiJP8m8AzoijZRhyFvqYFX4yw5Ykrftg2OHPJ16FUoMOlL4p6+cEgm+yUOKC+az++PhTjOuHJMHPAg+XkA==?iv=M2Vvnlu6pJcf6if1x7ef7g==",
    #     "sig": "2e8eaef67f40796be09be5a77b0ea7707e496484355774c13c078fbda4adb172301308dfc6d6256a2d65c33e5716dfd8efb1e6704cf5457ee723901ca1c7534c",
    # }

    # #
    # # connect to db
    # mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True)
    # db = mongo_client["dvmdash"]

    # result = db["events"].create_index([("id", 1)], unique=True)

    # insert event
    # result = db["events"].insert_one(test_event_1)

    # insert 2 events
    # try:
    #     result = db["events"].insert_many([test_event_1, test_event_3], ordered=False)
    # except BulkWriteError as e:
    #     # If you want to log the details of the duplicates or other errors
    #     for error in e.details["writeErrors"]:
    #         print(
    #             f"Error on inserting document with index {error['index']}: {error['errmsg']}"
    #         )

    # result = db["events"].insert_many([test_event_1, test_event_3], ordered=False)

    # print(result.inserted_ids)

    run_nostr_client()

    # result = db.events.count_documents({})
    # result = db.events.create_index([("id", 1)], unique=True)
    # print(result)

    pass
