"""
Test script to see which zaps have been paid to which DVMs
"""

from pymongo import MongoClient
import loguru
import os
import sys
from neo4j import (
    GraphDatabase,
    basic_auth,
    TrustCustomCAs,
    TrustSystemCAs,
    TRUST_SYSTEM_CA_SIGNED_CERTIFICATES,
)
from neo4j.exceptions import ServiceUnavailable
import json
import general.helpers as helpers
from tqdm import tqdm
import hashlib
from pathlib import Path
import dotenv
import ssl
from general.dvm import EventKind
import certifi
import time


def setup_logging():
    # Create a logs directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Configure the logger to use the DEBUG level
    loguru.logger.remove()  # Remove the default logger
    loguru.logger.add(sys.stderr, level="DEBUG")

    return loguru.logger


# set up logging

logger = setup_logging()
logger.info("Starting up in current directory: ", os.getcwd())


def setup_environment():
    env_path = Path(".env")
    if env_path.is_file():
        try:
            dotenv.load_dotenv(env_path, verbose=True, override=True)
            logger.info(f"Loaded environment from {env_path.resolve()}")
        except Exception as e:
            logger.error(f"Error loading environment from {env_path.resolve()}")
            logger.error(e)
            sys.exit(1)
    else:
        logger.error(f".env file not found at {env_path} ")
        raise FileNotFoundError(f".env file not found at {env_path} ")


setup_environment()


def setup_databases():
    if os.getenv("USE_MONGITA", None) is None:
        logger.warning(
            "USE_MONGITA is not set. Check that the env file is loading correctly."
        )

    if os.getenv("MONGO_URI", None) is None:
        logger.error("MONGO_URI is not set. Exiting")
        sys.exit(1)

    # This gets the path to the file containing trusted CA certificates.
    # This was needed to get this to work on a local mac, it may not be needed on a server linux machine
    ca = certifi.where()

    # connect to db
    mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=ca)
    db = mongo_client["dvmdash"]

    try:
        result = db["events"].count_documents({})
        logger.info(f"There are {result} documents in events collection")
    except Exception as e:
        logger.error("Could not count documents in db")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    logger.info("Connected to cloud mongo db")

    return db


def get_all_dvm_nip89_profiles(mongo_db):
    dvm_nip89_profiles = {}

    for nip89_event in mongo_db.events.find({"kind": 31990}):
        if "pubkey" in nip89_event:
            try:
                dvm_nip89_profiles[nip89_event["pubkey"]] = json.loads(
                    nip89_event["content"]
                )
                # print(
                #     f"Successfully loaded json from nip89 event for pubkey {nip89_event['pubkey']}"
                # )
            except Exception as e:
                # print(f"Error loading json from {nip89_event['content']}")
                # print(f"Content is: {nip89_event['content']}")
                # print(e)
                pass
    return dvm_nip89_profiles


def get_all_dvm_and_user_npubs(mongo_db):
    all_dvm_npubs = set()
    for event in mongo_db.events.find(
        {"kind": {"$gte": 6000, "$lte": 6999, "$nin": EventKind.get_bad_dvm_kinds()}}
    ):
        if "pubkey" in event:
            all_dvm_npubs.add(event["pubkey"])

    # get all pub keys from nip-89 profiles
    for nip89_event in mongo_db.events.find({"kind": 31990}):
        if "pubkey" in nip89_event:
            all_dvm_npubs.add(nip89_event["pubkey"])

    all_user_npubs = set()
    for event in mongo_db.events.find(
        {"kind": {"$gte": 5000, "$lte": 5999, "$nin": EventKind.get_bad_dvm_kinds()}}
    ):
        if "pubkey" in event and event["pubkey"] not in all_dvm_npubs:
            all_user_npubs.add(event["pubkey"])

    return all_dvm_npubs, all_user_npubs


if __name__ == "__main__":
    db = setup_databases()
    dvm_nip89_profiles = get_all_dvm_nip89_profiles(db)
    all_dvm_npubs, all_user_npubs = get_all_dvm_and_user_npubs(db)

    print(f"Number of DVMs: {len(all_dvm_npubs)}")
    print(f"Number of DVMs with NIP-89 profiles: {len(dvm_nip89_profiles)}")
    print(f"Number of users: {len(all_user_npubs)}")
    zap_events = list(db.events.find({"kind": 9735}))
    print(f"Number of zap events: {len(zap_events)}")

    for event in zap_events:
        if "pubkey" in event:
            if event["pubkey"] in all_dvm_npubs:
                print(f"\n======== Event: {event['id']}")
                print(f"\tthis event was created by a DVM: {event['pubkey']}")
            elif event["pubkey"] in all_user_npubs:
                print(f"\n======== Event: {event['id']}")
                print(f"\tthis event was created by a User: {event['pubkey']}")
            else:
                continue

        p_tag_value = next((tag[1] for tag in event["tags"] if tag[0] == "p"), None)
        upper_p_tag_value = next(
            (tag[1] for tag in event["tags"] if tag[0] == "P"), None
        )

        if p_tag_value:
            if p_tag_value in all_dvm_npubs:
                print(f"\tfound 'p' tag of a DVM: {p_tag_value}")
            elif p_tag_value in all_user_npubs:
                print(f"\tfound 'p' tag of a user: {p_tag_value}")

        if upper_p_tag_value:
            if upper_p_tag_value in all_dvm_npubs:
                print(f"\tfound 'P' tag of a DVM: {upper_p_tag_value}")
            elif upper_p_tag_value in all_user_npubs:
                print(f"\tfound 'P' tag of a user: {upper_p_tag_value}")
