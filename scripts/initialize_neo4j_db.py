"""
This script listens for updates to mongodb and triggers a function to update the dvm summary pages.
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

from general.graphdbsync import GraphDBSync


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
    if (
        os.getenv("USE_MONGITA", "False") != "False"
    ):  # use a local mongo db, like sqlite
        print("Using mongita")
        from mongita import MongitaClientDisk

        mongo_client = MongitaClientDisk()
        db = mongo_client.dvmdash
        print("Connected to local mongo db using MONGITA")

    else:
        # This gets the path to the file containing trusted CA certificates.
        # This was needed to get this to work on a local mac, it may not be needed on a server linux machine
        ca = certifi.where()

        # connect to db
        mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True, tlsCAFile=ca)
        db = mongo_client["dvmdash"]

        logger.info("Connected to cloud mongo db")

    try:
        result = db["events"].count_documents({})
        logger.info(f"There are {result} documents in events collection")
    except Exception as e:
        logger.error("Could not count documents in db")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    if os.getenv("USE_LOCAL_NEO4J", "False") != "False":
        # use local
        URI = os.getenv("NEO4J_LOCAL_URI")
        AUTH = (os.getenv("NEO4J_LOCAL_USERNAME"), os.getenv("NEO4J_LOCAL_PASSWORD"))

        neo4j_driver = GraphDatabase.driver(
            URI,
            auth=AUTH,
            # encrypted=True,
            # trust=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES,
        )

        neo4j_driver.verify_connectivity()
        logger.info("Verified connectivity to local Neo4j")
    else:
        URI = os.getenv("NEO4J_URI")
        AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))

        neo4j_driver = GraphDatabase.driver(
            URI,
            auth=AUTH,
            # encrypted=True,
            # trust=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES,
        )

        neo4j_driver.verify_connectivity()
        logger.info("Verified connectivity to cloud Neo4j")

    return db, neo4j_driver


if __name__ == "__main__":
    mongo_db, neo4j_driver = setup_databases()

    import logging

    logger = logging.getLogger()
    logger.setLevel(logging.ERROR)
    graph_sync = GraphDBSync(mongo_db, neo4j_driver, logger)
    print("About to clear neo4j db...")
    graph_sync.clear()
    print("About to sync...")
    graph_sync.run()

    # delete_all_relationships(neo4j_driver)
    # delete_all_nodes(neo4j_driver)
