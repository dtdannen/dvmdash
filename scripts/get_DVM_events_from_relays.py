import pymongo
from pymongo import MongoClient
import json
import os
import time
from pathlib import Path
from threading import Thread
import ctypes

import dotenv
from nostr_sdk import (
    Keys,
    Client,
    ClientSigner,
    Tag,
    EventBuilder,
    Filter,
    HandleNotification,
    Timestamp,
    nip04_decrypt,
)

from nostr_dvm.utils.dvmconfig import DVMConfig
from nostr_dvm.utils.nostr_utils import send_event, check_and_set_private_key
from nostr_dvm.utils.definitions import EventDefinitions

# connect to db
mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True)
db = mongo_client["dvmdash"]


RELAYS = os.getenv(
    "RELAYS",
    "wss://relay.damus.io,wss://blastr.f7z.xyz,wss://relayable.org,wss://nostr-pub.wellorder.net",
).split(",")

DVM_KINDS = [
    EventDefinitions.KIND_NIP90_EXTRACT_TEXT,
    EventDefinitions.KIND_NIP90_SUMMARIZE_TEXT,
    EventDefinitions.KIND_NIP90_TRANSLATE_TEXT,
    EventDefinitions.KIND_NIP90_GENERATE_TEXT,
    EventDefinitions.KIND_NIP90_GENERATE_IMAGE,
    EventDefinitions.KIND_NIP90_CONVERT_VIDEO,
    EventDefinitions.KIND_NIP90_GENERATE_VIDEO,
    EventDefinitions.KIND_NIP90_TEXT_TO_SPEECH,
    EventDefinitions.KIND_NIP90_CONTENT_DISCOVERY,
    EventDefinitions.KIND_NIP90_PEOPLE_DISCOVERY,
    EventDefinitions.KIND_NIP90_CONTENT_SEARCH,
    EventDefinitions.KIND_NIP90_GENERIC,
]


def write_events_to_db(events):
    if events:
        try:
            result = db["events"].insert_many(events, ordered=False)
            print(f"Finished writing events to db with result: {result}")
        except Exception as e:
            print(f"Error inserting events into database: {e}")



import threading
import time
from threading import Lock


class NotificationHandler(HandleNotification):
    def __init__(self):
        self.events = []
        self.lock = Lock()
        self.flush_interval = 15  # Flush every 10 seconds, adjust as needed
        self.stop_requested = False  # Flag to signal thread to stop

        # Start a thread to flush events periodically
        self.flush_thread = threading.Thread(target=self.flush_events_periodically)
        self.flush_thread.start()

    def handle(self, relay_url, event):
        # print(f"Received new event from {relay_url}: {event.as_json()}")
        if (
            event.kind() in DVM_KINDS or 6000 < event.kind() < 6999
        ):  # try catching new DVMs
            with self.lock:
                self.events.append(json.loads(event.as_json()))

    def flush_events(self):
        with self.lock:
            if self.events:
                print(f"Writing {len(self.events)} to db...")
                write_events_to_db(
                    self.events
                )  # Assuming this function writes a list of events to the DB
                self.events.clear()

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
    keys = Keys.from_sk_str(check_and_set_private_key("test_client"))
    sk = keys.secret_key()
    pk = keys.public_key()
    print(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()} ")
    signer = ClientSigner.keys(keys)
    client = Client(signer)
    for relay in RELAYS:
        client.add_relay(relay)
    client.connect()

    # dm_zap_filter = Filter().kinds([EventDefinitions.KIND_DM,
    #                                EventDefinitions.KIND_ZAP]).since(since_when_timestamp)

    # events to us specific
    dvm_filter = Filter().kinds(DVM_KINDS).since(since_when_timestamp)  # public events

    # client.subscribe([dm_zap_filter, dvm_filter])
    client.subscribe([dvm_filter])

    client.handle_notifications(NotificationHandler())
    while True:
        time.sleep(30.0)


def run_nostr_client(days=7):
    current_timestamp = Timestamp.now()
    current_secs = current_timestamp.as_secs()

    # 86400 seconds in a day
    day_secs = current_secs - int(days * 86400)
    a_week_ago = Timestamp.from_secs(day_secs)

    env_path = Path(".env")
    if env_path.is_file():
        print(f"loading environment from {env_path.resolve()}")
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f".env file not found at {env_path} ")

    nostr_dvm_thread = Thread(target=nostr_client, args=(a_week_ago,))
    nostr_dvm_thread.start()


if __name__ == "__main__":
    env_path = Path(".env")
    if env_path.is_file():
        print(f"loading environment from {env_path.resolve()}")
        dotenv.load_dotenv(env_path, verbose=True, override=True)
    else:
        raise FileNotFoundError(f".env file not found at {env_path} ")

    ### TEST CODE TO PUT AN EVENT INTO PYMONGO
    # test_event_1 = {
    #     "id": "a5b9b081a6d8f43581288ab8ec25f3d670ab77c9dfed3c9e5673fd52571b8794",
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
    # # connect to db
    # mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True)
    # db = mongo_client["dvmdash"]
    #
    # # result = db["events"].create_index([("id", 1)], unique=True)
    #
    # # insert event
    # result = db["events"].insert_one(test_event_1)
    #
    # print(result)

    run_nostr_client()
