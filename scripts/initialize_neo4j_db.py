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

import certifi


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

    URI = os.getenv("NEO4J_URI")
    AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))

    neo4j_driver = GraphDatabase.driver(
        URI,
        auth=AUTH,
        # encrypted=True,
        # trust=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES,
    )

    neo4j_driver.verify_connectivity()
    logger.info("Verified connectivity to Neo4j")

    return db, neo4j_driver


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


def create_npub(tx, npub_hex: str, npub: str, name: str = "") -> None:
    """
    Create a node in the Neo4j database with label 'NPub'.

    Parameters:
    tx (Transaction): The Neo4j transaction context.
    npub_hex (str): The hexadecimal representation of the public key.
    npub (str): The public key.
    name (str): The name of the person. Defaults to the first 8 characters of npub if not provided.

    Returns:
    None
    """
    # If name is not provided, use the first 8 characters of npub as the name
    if not name:
        name = npub[:8]

    # Define the Cypher query to create a node with the given properties only if it does not exist
    query = """
    MERGE (n:NPub {npub_hex: $npub_hex})
    ON CREATE SET n.npub = $npub, n.name = $name
    """

    # Execute the query with the provided parameters
    tx.run(query, npub_hex=npub_hex, npub=npub, name=name)


# Function to create a hash of the content string
def generate_content_hash(content: str) -> str:
    """
    Generate an SHA-256 hash for the given content string.

    Parameters:
    content (str): The content string to be hashed.

    Returns:
    str: The SHA-256 hash of the content.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# Function to create a content node if it does not already exist
def create_content(
    tx, content: str, content_orig_event_id: str, max_size: int = 1000
) -> None:
    """
    Create a node in the Neo4j database with label 'Content' using a hash of the content to prevent duplicates.

    Parameters:
    tx (Transaction): The Neo4j transaction context.
    content (str): The content string.
    content_orig_event_id (str): The id of the event that has the content
    max_size (int): The maximum allowed size for the content in bytes.

    Returns:
    None
    """
    # Measure the size of the content in bytes
    byte_size = len(content.encode("utf-8"))

    # Check if the content size is within the allowed limit
    if byte_size <= max_size:
        # Define the Cypher query to create a node with the given properties only if it does not exist
        query = """
        MERGE (c:Content {content_id: $content_orig_event_id})
        ON CREATE SET c.content = $content
        """
        tx.run(query, content_orig_event_id=content_orig_event_id, content=content)
        print(f"Content node created or already exists: {content_orig_event_id}")
    else:
        print(f"Content too large to create node: size: {byte_size} bytes")


def create_created_for_relationship(
    tx, npub_hex: str, content_orig_event_id: str
) -> None:
    """
    Create a relationship in the Neo4j database between an NPub node and a Content node.

    Parameters:
    tx (Transaction): The Neo4j transaction context.
    npub_hex (str): The hexadecimal representation of the public key.
    content_orig_event_id (str): The id of the event that has the content

    Returns:
    None
    """
    # Define the Cypher query to create a relationship between the NPub and Content nodes
    query = """
    MATCH (n:NPub {npub_hex: $npub_hex})
    MATCH (c:Content {content_id: $content_orig_event_id})
    MERGE (c)-[:CREATED_FOR]->(n)
    """

    # Execute the query with the provided parameters
    tx.run(query, npub_hex=npub_hex, content_orig_event_id=content_orig_event_id)


def process_notes_into_neo4j(mongo_db, neo4j_driver):
    all_dvm_request_events = list(
        mongo_db.events.find({"kind": {"$gte": 5000, "$lte": 5999}})
    )

    # remove 5666
    all_dvm_request_events = [
        event for event in all_dvm_request_events if event["kind"] not in [5666]
    ]
    logger.info(f"Loaded {len(all_dvm_request_events)} dvm request events from mongo")

    all_dvm_response_events = list(
        mongo_db.events.find({"kind": {"$gte": 6000, "$lte": 6999}})
    )

    # remove 6666
    all_dvm_response_events = [
        event for event in all_dvm_response_events if event["kind"] not in [6666]
    ]

    logger.info(f"Loaded {len(all_dvm_response_events)} dvm response events from mongo")

    dvm_nip89_profiles = get_all_dvm_nip89_profiles(mongo_db)
    logger.info(f"Loaded {len(dvm_nip89_profiles)} dvm nip89 profiles")

    with neo4j_driver.session() as session:
        # first, create all nodes for all npubs
        # for event in tqdm(all_dvm_request_events + all_dvm_response_events):
        #     npub_hex = event["pubkey"]
        #     npub = helpers.hex_to_npub(npub_hex)
        #
        #     name = ""
        #     if npub_hex in dvm_nip89_profiles:
        #         name = dvm_nip89_profiles[npub_hex].get("name", "")
        #
        #     create_npub(session, npub_hex, npub, name)

        # second, create content nodes for all DVM response events and create relationship between
        for event in tqdm(all_dvm_response_events):
            if "content" not in event:
                logger.warning(
                    f"Event {event['id']} for kind {event['kind']} does not have content field"
                )
                continue

            content_payload_str = event["content"]
            content_orig_event_id = event["id"]

            create_content(session, content_payload_str, content_orig_event_id)

            customer_npub_hex = next(
                (tag[1] for tag in event["tags"] if tag[0] == "p"), None
            )

            if customer_npub_hex is None:
                # try to get it from the request tag
                request_tag_content = next(
                    (
                        req_tag[1]
                        for req_tag in event["tags"]
                        if req_tag[0] == "request"
                    ),
                    None,
                )

                if request_tag_content:
                    request_tag_content = json.loads(request_tag_content)
                    if "pubkey" in request_tag_content:
                        customer_npub_hex = request_tag_content["pubkey"]
                        logger.warning(
                            "Got customer npub from request tag because it was not in the 'p' tag"
                        )
            else:
                logger.info("Got customer npub from 'p' tag")
                pass

            if customer_npub_hex is None:
                logger.warning(
                    f"Event {event['id']} for kind {event['kind']} does not have a customer npub"
                )
                continue

            if customer_npub_hex:
                create_created_for_relationship(
                    session,
                    customer_npub_hex,
                    content_orig_event_id,
                )
                logger.info(
                    f"A relationship was created between {helpers.hex_to_npub(customer_npub_hex)} and {content_orig_event_id}"
                )


if __name__ == "__main__":
    mongo_db, neo4j_driver = setup_databases()
    process_notes_into_neo4j(mongo_db, neo4j_driver)
