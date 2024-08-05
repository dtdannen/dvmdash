import asyncio
from asyncio import Queue
import ast
from collections import deque
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
from general.helpers import hex_to_npub


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
        # EventKind.DM.value,
        # EventKind.ZAP.value,
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
# RELEVANT_KINDS = [Kind(1)]

GLOBAL_STOP = False
RESTART_THRESHOLD = 0.2


class NotificationHandler(HandleNotification):
    def __init__(self, max_batch_size=100, max_wait_time=5):
        self.event_queue = Queue()
        self.neo4j_queue = Queue()  # this is for neo4j queries that need to go out
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.bin_size_seconds = 15  # seconds
        self.seen_events_bin = [
            (0, 0.0)
        ]  # (v1, v2) where v1 is the number of seen events in that bin and v2 is the difference (%) from the last bin
        self.last_bin_created_at_time = Timestamp.now()

    def count_new_seen_event(self):
        # check if we are in the current bin or need to create a new bin
        current_time = Timestamp.now()
        last_bin_event_count = self.seen_events_bin[-1][0]
        last_bin_event_delta = self.seen_events_bin[-1][1]

        # we need to create a new bin, counting this new single event
        if current_time - self.last_bin_created_at_time > self.bin_size_seconds:
            ## check if the last bin was lower than the restart threshold
            LOGGER.info(
                f"Creating a new bin, last one's delta was: {last_bin_event_delta}"
            )
            # if self.seen_events_bin[-1][1] < RESTART_THRESHOLD:
            #     global GLOBAL_STOP
            #     GLOBAL_STOP = True

            self.last_bin_created_at_time = current_time

            if last_bin_event_count == 0:
                last_bin_delta_percent = 1.0
            else:
                last_bin_delta_percent = 1 / last_bin_event_count

            self.seen_events_bin.append((1, last_bin_delta_percent))
        else:
            # add 1 to the current event counter and update the delta
            new_event_count = self.seen_events_bin[-1][0] + 1

            if last_bin_event_count == 0:
                last_bin_delta_percent = 1.0 * new_event_count
            else:
                last_bin_delta_percent = new_event_count / last_bin_event_count

            self.seen_events_bin[-1] = (new_event_count, last_bin_delta_percent)

    async def handle(self, relay_url, subscription_id, event: Event):
        # self.count_new_seen_event()
        if event.kind() in RELEVANT_KINDS:
            await self.event_queue.put(json.loads(event.as_json()))

        LOGGER.info(f"Current queue size: {self.event_queue.qsize()}")

    async def handle_msg(self, relay_url: str, message: str):
        # Implement this method
        pass

    async def process_events(self):
        while True:
            batch = []
            try:
                # Wait for the first event or until max_wait_time
                event = await asyncio.wait_for(
                    self.event_queue.get(), timeout=self.max_wait_time
                )
                batch.append(event)

                # Collect more events if available, up to max_batch_size
                while len(batch) < self.max_batch_size and not self.event_queue.empty():
                    batch.append(self.event_queue.get_nowait())

                # LOGGER.info(f"Batch size is now {len(batch)}")

            except asyncio.TimeoutError:
                # If no events received within max_wait_time, continue to next iteration
                continue

            if batch:
                await self.async_write_to_mongo_db(batch)
                await self.create_neo4j_queries(batch)

            # Mark tasks as done
            number_of_events_marked_done = 0
            for _ in range(len(batch)):
                self.event_queue.task_done()
                number_of_events_marked_done += 1
            LOGGER.info(f"Current queue size: {self.event_queue.qsize()}")
            # LOGGER.info(f"Number of events marked done: {number_of_events_marked_done}")
            # LOGGER.info(f"Remaining items in queue: {remaining_items}")

    async def async_write_to_mongo_db(self, events):
        LOGGER.info(f"Current queue size: {self.event_queue.qsize()}")
        if len(events) > 0:
            try:
                result = await ASYNC_MONGO_DB.test_events.insert_many(
                    events, ordered=False
                )
                # LOGGER.info(
                #     f"Finished writing events to db with result: {len(result.inserted_ids)}"
                # )
            except BulkWriteError as e:
                # If you want to log the details of the duplicates or other errors
                num_duplicates_found = len(e.details["writeErrors"])
                LOGGER.warning(
                    f"Ignoring {num_duplicates_found} / {len(events)} duplicate events...",
                    end="",
                )
            except Exception as e:
                LOGGER.error(f"Error inserting events into database: {e}")

    async def process_neo4j_queries(self):
        while True:
            batch = []
            try:
                # Wait for the first event or until max_wait_time
                query = await asyncio.wait_for(
                    self.neo4j_queue.get(), timeout=self.max_wait_time
                )
                batch.append(query)

                # Start a new transaction
                async with NEO4J_DRIVER.session().begin_transaction() as tx:
                    for query in batch:
                        # Execute each query within the transaction
                        await tx.run(query["query"], **query["params"])

                    # Commit the transaction
                    await tx.commit()

                LOGGER.info(
                    f"Successfully executed batch of {len(batch)} queries in Neo4j"
                )
            except Exception as e:
                LOGGER.error(f"Error executing batch queries in Neo4j: {str(e)}")

    async def create_neo4j_queries(self, events):
        LOGGER.info(f"Current queue size: {self.event_queue.qsize()}")
        if not events:
            return

        for event in events:
            # Step 1: figure out what additional labels this event will get
            additional_event_labels = []
            additional_properties = {}
            if 5000 <= event["kind"] < 6000:
                additional_event_labels = ["DVMRequest"]
            elif 6000 <= event["kind"] < 6999:
                additional_event_labels = ["DVMResult"]
            elif event["kind"] == 7000:
                # print("event is kind 7000")
                additional_event_labels.append("Feedback")
                # check the tags
                if "tags" in event:
                    tags = ast.literal_eval(event["tags"])
                    for tag in tags:
                        # print(f"\ttag is {tag}")
                        if (
                            len(tag) > 1
                            and tag[0] == "status"
                            and tag[1] == "payment-required"
                        ):
                            additional_event_labels.append("FeedbackPaymentRequest")
                        elif len(tag) > 1 and tag[0] == "amount":
                            additional_properties["amount"] = tag[1]
                            if len(tag) > 2:
                                additional_properties["invoice_data"] = tag[2]

            if additional_event_labels:
                # create the event node
                event_query = (
                    """
                        MERGE (n:Event:"""
                    + ":".join(additional_event_labels)
                    + """ {id: $event_id})
                        ON CREATE SET n = apoc.convert.fromJsonMap($json)
                        ON MATCH SET n += apoc.convert.fromJsonMap($json)
                        RETURN n
                        """
                )

            else:
                # create the event node
                event_query = """
                        MERGE (n:Event {id: $event_id})
                        ON CREATE SET n = apoc.convert.fromJsonMap($json)
                        ON MATCH SET n += apoc.convert.fromJsonMap($json)
                        RETURN n
                        """

            # do this in this order, so we keep any top level event properties from the original note and don't
            # accidentally overwrite them
            for prop_k, prop_v in additional_properties.items():
                if prop_k not in event.keys():
                    event[prop_k] = prop_v
                else:
                    LOGGER.warning(
                        f"Event {event['id']} already has property {prop_k} with a "
                        f"value of {event[prop_k]} and we are trying to add property value {prop_v}"
                    )

            # Step 2: Submit the query for creating this event to neo4j
            ready_to_execute_event_query = {
                "query": event_query,
                "params": {"event_id": event["id"], "json": json.dumps(event)},
            }
            await self.neo4j_queue.put(ready_to_execute_event_query)

            # Step 3: Determine what other nodes and relations to also submit based on additional_event_labels
            if additional_event_labels == ["DVMRequest"]:
                # if this is a DVMRequest, then we need (1) a User Node and (2) a MADE_EVENT relation
                user_node_query = """
                    MERGE (n:User {npub_hex: $npub_hex})
                    ON CREATE SET n = apoc.convert.fromJsonMap($json)
                    ON MATCH SET n += apoc.convert.fromJsonMap($json)
                    RETURN n
                """

                user_npub = hex_to_npub(event["pubkey"])
                user_node_query_params = {
                    "npub_hex": event["pubkey"],
                    "json": {
                        "npub": user_npub,
                        "url": "https://dvmdash.live/npub/" + user_npub,
                        "neo4j_node_type": "User",
                    },
                }

                # TODO - later we can submit a request to relays to get a kind 0 profile for the USER and add
                #  these values to the params

                ready_to_execute_user_query = {
                    "query": user_node_query,
                    "params": user_node_query_params,
                }

                await self.neo4j_queue.put(ready_to_execute_user_query)

                # now do the MADE_EVENT relation
                made_event_query = """
                    MATCH (n:User {npub_hex: $npub_hex})
                    MATCH (r:Event {id: $event_id})
                    MERGE (n)-[rel:MADE_EVENT]->(r)
                    RETURN rel
                """

                ready_to_execute_made_event_query = {
                    "query": made_event_query,
                    "params": {
                        "npub_hex": event["pubkey"],
                        "event_id": event["id"],
                    },
                }

                await self.neo4j_queue.put(ready_to_execute_made_event_query)
            elif additional_event_labels == ["DVMResult"]:
                # let's get the 'e' tag pointing to the original request and if we can't find it, reject this event
                dvm_request_event_id = ""
                for tag in event["tags"]:
                    if len(tag) > 1 and tag[0] == "e":
                        dvm_request_event_id = tag[1]
                        break

                if dvm_request_event_id:
                    dvm_node_query = """
                        MERGE (n:DVM {npub_hex: $npub_hex})
                        ON CREATE SET n = apoc.convert.fromJsonMap($json)
                        RETURN n
                    """

                    dvm_npub = hex_to_npub(event["pubkey"])
                    dvm_node_query_params = {
                        "npub_hex": event["pubkey"],
                        "json": {
                            "npub": dvm_npub,
                            "url": "https://dvmdash.live/dvm/" + dvm_npub,
                            "neo4j_node_type": "DVM",
                        },
                    }

                    # TODO - later we can submit a request to relays to get a kind 31990 profile for the DVM and add
                    #  these values to the dvm node params

                    ready_to_execute_dvm_node_query = {
                        "query": dvm_node_query,
                        "params": dvm_node_query_params,
                    }

                    await self.neo4j_queue.put(ready_to_execute_dvm_node_query)

                    # now create the MADE_EVENT relation query

                    dvm_made_event_query = """
                       MATCH (n:DVM {npub_hex: $npub_hex})
                       MATCH (r:Event {id: $event_id})
                       MERGE (n)-[rel:MADE_EVENT]->(r)
                       RETURN rel
                    """

                    ready_to_execute_dvm_made_event_query = {
                        "query": dvm_made_event_query,
                        "params": {
                            "npub_hex": event["pubkey"],
                            "event_id": event["id"],
                        },
                    }

                    await self.neo4j_queue.put(ready_to_execute_dvm_made_event_query)

                    # now because this is a DVMResult, we want to add a relation from this to the original DVM Request

                    # now let's make the query to create that node in case it doesn't exist
                    create_dvm_request_if_not_exist_query = """
                        OPTIONAL MATCH (existing:Event:DVMRequest {id: $event_id})
                        WITH existing
                        WHERE existing IS NULL
                        CREATE (n:Event:DVMRequest {id: $event_id})
                        RETURN n
                    """

                    ready_to_execute_create_dvm_request_if_not_exist = {
                        "query": create_dvm_request_if_not_exist_query,
                        "params": {"event_id": dvm_request_event_id},
                    }

                    await self.neo4j_queue.put(
                        ready_to_execute_create_dvm_request_if_not_exist
                    )

                    # now make the relation from the DVMResult to the DVMRequest

                    dvm_result_to_request_relation_query = """
                        MATCH (result:Event:DVMResult {id: $result_event_id})
                        MATCH (request:Event:DVMRequest {id: $request_event_id})
                        MERGE (result)-[rel:RESULT_FOR]->(request)
                        RETURN rel
                    """

                    ready_to_execute_dvm_result_to_request_rel_query = {
                        "query": dvm_result_to_request_relation_query,
                        "params": {
                            "result_event_id": event["id"],
                            "request_event_id": dvm_request_event_id,
                        },
                    }

                    await self.neo4j_queue.put(
                        ready_to_execute_dvm_result_to_request_rel_query
                    )

                else:
                    LOGGER.warning(
                        f"Rejecting DVMResult event with id: {event['id']} because there is no 'e' tag"
                    )
            elif "Feedback" in additional_event_labels:
                # let's get the 'e' tag pointing to the original request and if we can't find it, reject this event
                dvm_request_event_id = ""
                for tag in event["tags"]:
                    if len(tag) > 1 and tag[0] == "e":
                        dvm_request_event_id = tag[1]
                        break

                if dvm_request_event_id:
                    # let's create an invoice node if there is one
                    if "FeedbackPaymentRequest" in additional_event_labels:
                        if "invoice" in additional_properties:
                            # for now we use the invoice data as a unique identifier, mostly supporting the lnbc
                            # string format
                            if not additional_properties["invoice"].startswith("lnbc"):
                                # TODO - add better support for other payment request types, like ecash
                                LOGGER.warning(
                                    f"invoice data for feedback event {event['id']} does not start with 'lnbc'"
                                )
                            invoice_params = {
                                "invoice_data": additional_properties["invoice_data"],
                                "url": f"https://dvmdash.live/invoice/{additional_properties['invoice_data']}",
                            }
                            if "amount" in additional_properties:
                                invoice_params["amount"] = additional_properties[
                                    "amount"
                                ]

                            create_invoice_node_query = """
                                                    MERGE (n:Invoice {id: $invoice_data})
                                                    ON CREATE SET n += apoc.convert.fromJsonMap($json)
                                                    ON MATCH SET n += apoc.convert.fromJsonMap($json)
                                                    RETURN n
                                                """
                            invoice_params = {
                                "creator_pubkey": event["pubkey"],
                                "feedback_event_id": event["id"],
                            }

                            ready_to_execute_create_invoice_node_query = {
                                "query": create_invoice_node_query,
                                "params": invoice_params,
                            }

                            # TODO - put this event into a mongo collection for invoices so we can display this on the webpage

                            await self.neo4j_queue.put(
                                ready_to_execute_create_invoice_node_query
                            )

                            # now create a relation to this invoice from the feedback event
                            create_invoice_to_feedback_rel_query = """
                                MATCH (i:Invoice {id: $invoice_data})
                                MATCH (f:Event {id: $event_id})
                                MERGE (i)-[rel:INVOICE_FROM]->(f)
                                RETURN rel
                            """

                            invoice_rel_params = {
                                "invoice_data": additional_properties["invoice_data"],
                                "event_id": event["id"],
                            }

                            ready_to_execute_invoice_to_feedback_rel = {
                                "query": create_invoice_to_feedback_rel_query,
                                "params": invoice_rel_params,
                            }

                            await self.neo4j_queue.put(
                                ready_to_execute_invoice_to_feedback_rel
                            )

                        else:
                            LOGGER.debug(
                                f"FeedbackPaymentRequest event id={event['id']} is missing invoice data"
                            )

                    # now create a relation from the feedback to the original DVM Request
                    create_feedback_to_original_request_query = """
                       MATCH (feedback:Event {id: $feedback_event_id})
                       MATCH (request:Event {id: $request_event_id})
                       MERGE (feedback)-[rel:FEEDBACK_FOR]->(request)
                       RETURN rel
                   """

                    ready_to_execute_feedback_to_request_rel_query = {
                        "query": create_feedback_to_original_request_query,
                        "params": {
                            "feedback_event_id": event["id"],
                            "request_event_id": dvm_request_event_id,
                        },
                    }

                    await self.neo4j_queue.put(
                        ready_to_execute_feedback_to_request_rel_query
                    )

    def _create_user_node(self, user_npub):
        """
        Attempts to look for a user's kind 0 profile event and update the user node for this npub
        """

        # ask relays for a kind 0 by this npub

        # if we find one, add it to the neo4j Queue

    def _create_event_node_insert_queries(self, neo4j_event):
        """handles making labels and other stuff"""
        # create different events based on the kind
        additional_event_labels = []
        additional_queries = (
            []
        )  # list of tuples, where the item[0] is the query and item[1] is the args
        if 5000 <= neo4j_event["kind"] < 6000:
            additional_event_labels = ["DVMRequest"]
            # nothing else is needed for this
        elif 6000 <= neo4j_event["kind"] < 6999:
            additional_event_labels = ["DVMResult"]
            # we need to connect this DVMResult with the original DVMRequest Event

        elif neo4j_event["kind"] == 7000:
            # print("event is kind 7000")
            additional_event_labels.append("Feedback")
            # check the tags
            if "tags" in neo4j_event:
                tags = ast.literal_eval(neo4j_event["tags"])
                for tag in tags:
                    # print(f"\ttag is {tag}")
                    if (
                        tag[0] == "status"
                        and len(tag) > 1
                        and tag[1] == "payment-required"
                    ):
                        additional_event_labels.append("FeedbackPaymentRequest")
                        # print("\tadding the label FeedbackPaymentRequest")

        if additional_event_labels:
            # create the event node
            query = (
                """
                MERGE (n:Event:"""
                + ":".join(additional_event_labels)
                + """ {id: $event_id})
                    ON CREATE SET n = apoc.convert.fromJsonMap($json)
                    ON MATCH SET n += apoc.convert.fromJsonMap($json)
                    RETURN n
                    """
            )
        else:
            # create the event node
            query = """
                    MERGE (n:Event {id: $event_id})
                    ON CREATE SET n = apoc.convert.fromJsonMap($json)
                    ON MATCH SET n += apoc.convert.fromJsonMap($json)
                    RETURN n
                    """

        return query

    def create_neo4j_queries_from_single_event(self, event):
        event_kind = int(event.get("kind"))
        event_id = str(event.get("id"))
        pubkey = event.get("pubkey")

        async with NEO4J_DRIVER.session() as session:
            try:
                # Create Event node
                event_query = self._create_event_node_insert_query(event)
                event_props = {
                    k: v for k, v in event.items() if k not in ["_id", "tags"]
                }
                await session.run(
                    event_query, event_id=event_id, event_props=event_props
                )

                # Create User or DVM node and relationship
                if 5000 <= event_kind < 6000:
                    node_type = "User"
                    rel_type = "MADE_EVENT"
                elif 6000 <= event_kind < 7000 or event_kind == 7000:
                    node_type = "DVM"
                    rel_type = "MADE_EVENT"
                else:
                    node_type = "Unknown"
                    rel_type = "ASSOCIATED_WITH"

                node_query = f"""
                MERGE (n:{node_type} {{npub_hex: $pubkey}})
                SET n.npub = $npub, n.url = $url
                WITH n
                MATCH (e:Event {{id: $event_id}})
                MERGE (n)-[:{rel_type}]->(e)
                """
                npub = hex_to_npub(pubkey)
                url = f"https://dvmdash.live/{'dvm' if node_type == 'DVM' else 'npub'}/{npub}"
                await session.run(
                    node_query, pubkey=pubkey, npub=npub, url=url, event_id=event_id
                )

                # Handle specific event types
                if event_kind == 7000:  # Feedback event
                    feedback_query = """
                    MATCH (f:Event {id: $feedback_id})
                    MATCH (r:Event {id: $request_id})
                    MERGE (f)-[:FEEDBACK_FOR]->(r)
                    """
                    request_event_id = next(
                        (tag[1] for tag in event.get("tags", []) if tag[0] == "e"), None
                    )
                    if request_event_id:
                        await session.run(
                            feedback_query,
                            feedback_id=event_id,
                            request_id=request_event_id,
                        )

                    # Handle invoice if present
                    invoice_query = """
                    MERGE (i:Invoice {id: $invoice_id})
                    SET i += $invoice_props
                    WITH i
                    MATCH (f:Event {id: $feedback_id})
                    MERGE (i)-[:INVOICE_FROM]->(f)
                    """
                    for tag in event.get("tags", []):
                        if (
                            tag[0] == "amount"
                            and len(tag) >= 3
                            and tag[2].startswith("lnbc")
                        ):
                            invoice_props = {
                                "amount": tag[1],
                                "invoice": tag[2],
                                "creator_pubkey": pubkey,
                                "feedback_event_id": event_id,
                                "url": f"https://dvmdash.live/event/{tag[2]}",
                            }
                            await session.run(
                                invoice_query,
                                invoice_id=tag[2],
                                invoice_props=invoice_props,
                                feedback_id=event_id,
                            )

                LOGGER.info(f"Successfully processed event {event_id} in Neo4j")
            except Exception as e:
                LOGGER.error(f"Error processing event {event_id} in Neo4j: {str(e)}")


async def nostr_client():
    keys = Keys.generate()
    pk = keys.public_key()
    LOGGER.info(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()} ")
    signer = NostrSigner.keys(keys)
    client = Client(signer)
    for relay in RELAYS:
        await client.add_relay(relay)
    await client.connect()

    prev_24hr_timestamp = Timestamp.from_secs(Timestamp.now().as_secs() - 60 * 60 * 24)

    dvm_filter = Filter().kinds(RELEVANT_KINDS).since(prev_24hr_timestamp)
    await client.subscribe([dvm_filter])

    # Your existing code without the while True loop
    notification_handler = NotificationHandler()
    process_events_task = asyncio.create_task(notification_handler.process_events())
    process_neo4j_queries = asyncio.create_task(
        notification_handler.process_neo4j_queries()
    )
    await client.handle_notifications(notification_handler)
    return client  # Return the client for potential cleanup


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


def async_db_tests():
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
    loop = asyncio.get_event_loop()
    client = loop.run_until_complete(nostr_client())
    # TODO - get async to end if GLOBAL_STOP is true.... probably just need to use an asyncio function to get
    #  the current loop and end all tasks on it
    #  THEN wrap all this code in the main function so it gets called again EXCEPT if there is a keyboard interrupt
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(client.disconnect())
        loop.close()
