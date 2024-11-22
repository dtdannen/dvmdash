import asyncio
from asyncio import Queue
import sys
import nostr_sdk
import json
import os
import time
from pathlib import Path
import loguru
import dotenv
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
    NostrError,
)
from neo4j import AsyncGraphDatabase
import motor.motor_asyncio
import pymongo  # used only to create new collections if they don't exist
from pymongo.errors import BulkWriteError, InvalidOperation
from general.dvm import EventKind
from general.helpers import hex_to_npub, sanitize_json, format_query_with_params
import traceback
import argparse
import datetime

# import dumps from bson
from bson.json_util import dumps
from bson import ObjectId


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


def sync_databases():
    LOGGER.info(f"USE_MONGITA: {os.getenv('USE_MONGITA', False)}")

    # Connect to old db
    old_sync_db_client = pymongo.MongoClient(os.getenv("OLD_MONGO_URI"))
    old_sync_db = old_sync_db_client["dvmdash"]

    # Connect to new db
    sync_db_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
    sync_db = sync_db_client["dvmdash"]

    # Set batch size
    BATCH_SIZE = 1000

    try:
        # Get total number of documents for progress tracking
        total_documents = old_sync_db.events.count_documents({})
        processed_documents = 0

        # Iterate through documents in batches
        last_id = None

        while True:
            # Use _id for pagination instead of skip
            query = {} if last_id is None else {"_id": {"$gt": last_id}}
            batch = list(old_sync_db.events.find(query).limit(BATCH_SIZE))

            if not batch:
                break

            # Prepare documents for insertion, ignoring old ObjectIDs
            new_batch = []
            for doc in batch:
                new_doc = doc.copy()
                del new_doc["_id"]  # Remove old ObjectId
                new_batch.append(new_doc)

            try:
                result = sync_db.prod_events.insert_many(new_batch, ordered=False)
                inserted_count = len(result.inserted_ids)
                LOGGER.info(f"Inserted {inserted_count} documents")
            except BulkWriteError as e:
                inserted_count = e.details["nInserted"]
                num_duplicates = len(e.details["writeErrors"])
                LOGGER.warning(
                    f"Inserted {inserted_count} documents, ignored {num_duplicates} duplicates"
                )

            processed_documents += len(batch)
            progress = (processed_documents / total_documents) * 100
            LOGGER.info(
                f"Progress: {progress:.2f}% ({processed_documents}/{total_documents})"
            )

            # Update last_id for next iteration
            last_id = batch[-1]["_id"]

    except InvalidOperation as e:
        LOGGER.error(f"MongoDB InvalidOperation: {e}")
        LOGGER.error(
            f"This error often occurs when trying to modify a cursor after executing a query."
        )
        LOGGER.error(
            f"Check if you're trying to modify the cursor after iterating through it."
        )
    except Exception as e:
        LOGGER.error(f"Error during database synchronization: {e}")
        LOGGER.error(f"Error type: {type(e).__name__}")
    finally:
        # Close database connections
        old_sync_db_client.close()
        sync_db_client.close()


if __name__ == "__main__":
    sync_databases()
