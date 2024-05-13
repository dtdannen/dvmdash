import sys

print(sys.path)

import os
import loguru
from nostr_sdk import (
    Keys,
    Client,
    NostrSigner,
    EventBuilder,
    Filter,
    Metadata,
    Nip46Signer,
    init_logger,
    LogLevel,
    NostrConnectUri,
    Kind,
    Timestamp,
)
from datetime import timedelta
import time
from pathlib import Path
from pymongo import MongoClient
import dotenv
from pymongo.errors import BulkWriteError

from general.dvm import EventKind


# init logger
logger = loguru.logger

# get environment variables
env_path = Path(".env")
if env_path.is_file():
    logger.info(f"loading environment from {env_path.resolve()}")
    dotenv.load_dotenv(env_path, verbose=True, override=True)
else:
    logger.error(f".env file not found at {env_path} ")
    raise FileNotFoundError(f".env file not found at {env_path} ")


def setup_db():
    logger.debug("os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False))

    if (
        os.getenv("USE_MONGITA", "False") != "False"
    ):  # use a local mongo db, like sqlite
        logger.debug(
            "os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False)
        )
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

    return db


def get_events_from_relays(relays, client_private_key):
    # Initialize client with private key
    # (this could be unique every time if there are problems later)
    keys = Keys.parse(client_private_key)
    signer = NostrSigner.keys(keys)
    client = Client(signer)

    # Add relays and connect
    client.add_relays(relays)
    client.connect()

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

    all_kinds = all_kinds - set(EventKind.get_bad_dvm_kinds())

    all_kinds = [Kind(k) for k in all_kinds]

    half_day_in_seconds = 60 * 60 * 12
    max_time = Timestamp.from_secs(Timestamp.now().as_secs() - half_day_in_seconds)

    # Get events from relays
    logger.info("Getting events from relays...")
    dvm_filter = Filter().kinds(all_kinds).since(max_time)

    # TODO - this is the line to change
    events = client.get_events_of([dvm_filter], timedelta(seconds=10))

    return events


def write_events_to_db(events, db):
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


if __name__ == "__main__":
    relays = os.getenv(
        "RELAYS",
        "wss://relay.damus.io,wss://blastr.f7z.xyz,wss://relayable.org,wss://nostr-pub.wellorder.net",
    ).split(",")

    client_private_key = os.getenv("DVM_PRIVATE_KEY_TEST_CLIENT", None)

    if client_private_key is None:
        logger.error("CLIENT_PRIVATE_KEY is None")
        raise ValueError("CLIENT_PRIVATE_KEY is None")

    db = setup_db()
    events = get_events_from_relays(relays, client_private_key)
    write_events_to_db(events, db)
    logger.info("Done")
