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
)
from neo4j import AsyncGraphDatabase
import motor.motor_asyncio
import pymongo  # used only to create new collections if they don't exist
from pymongo.errors import BulkWriteError
from general.dvm import EventKind
from general.helpers import hex_to_npub, sanitize_json, format_query_with_params
import traceback
import argparse
import datetime


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
NEO4J_BOOKMARK_MANAGER = AsyncGraphDatabase.bookmark_manager()


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
    def __init__(self, max_batch_size=100, max_wait_time=3):
        self.event_queue = Queue()
        self.neo4j_queue = Queue()  # this is for neo4j queries that need to go out
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.bin_size_seconds = 15  # seconds
        self.seen_events_bin = [
            (0, 0.0)
        ]  # (v1, v2) where v1 is the number of seen events in that bin and v2 is the difference (%) from the last bin
        self.last_bin_created_at_time = Timestamp.now()
        self.row_count = 0
        self.last_header_time = 0
        self.header_interval = 20  # Print header every 20 rows
        self.neo4j_semaphore = asyncio.Semaphore(3)

    def count_new_seen_event(self):
        """
        WIP: If we start getting an unusual low number of events, report the issue somewhere automatically
        """
        # TODO - this hasn't been tested yet
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

    async def print_queue_sizes(self):
        current_time = time.time()
        event_queue_size = self.event_queue.qsize()
        neo4j_queue_size = self.neo4j_queue.qsize()

        # Print header if it's the first row or if header_interval rows have passed
        if (
            self.row_count % self.header_interval == 0
            or current_time - self.last_header_time > 60
        ):
            header = f"{'Time':^12}|{'Event Queue':^15}|{'Neo4j Queue':^15}"
            # LOGGER.info("\n" + "=" * len(header))
            LOGGER.info(header)
            LOGGER.info("=" * len(header))
            self.last_header_time = current_time
            self.row_count = 0

        # Print the queue sizes
        current_time_str = time.strftime("%H:%M:%S")
        LOGGER.info(
            f"{current_time_str:^12}|{event_queue_size:^15d}|{neo4j_queue_size:^15d}"
        )

        self.row_count += 1

    async def handle(self, relay_url, subscription_id, event: Event):
        # self.count_new_seen_event()
        if event.kind() in RELEVANT_KINDS:
            await self.event_queue.put(json.loads(event.as_json()))

        await self.print_queue_sizes()

    async def handle_msg(self, relay_url: str, message: str):
        # Implement this method
        pass

    async def manual_insert(self, event_json):
        """
        Manually insert an event into the system.

        :param event_json: A JSON string representing the event to be inserted.
        """
        # Convert the JSON string back to an Event object
        event = Event.from_json(event_json)

        # Check if the event kind is relevant
        if event.kind() in RELEVANT_KINDS:
            await self.event_queue.put(json.loads(event.as_json()))

            # Optionally, call print_queue_sizes or any other method to handle the event as needed
            await self.print_queue_sizes()

    async def process_events(self):
        while True:
            try:
                await self.print_queue_sizes()
                batch = []
                try:
                    # Wait for the first event or until max_wait_time
                    event = await asyncio.wait_for(
                        self.event_queue.get(), timeout=self.max_wait_time
                    )
                    batch.append(event)

                    # Collect more events if available, up to max_batch_size
                    while (
                        len(batch) < self.max_batch_size
                        and not self.event_queue.empty()
                    ):
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
                # LOGGER.info(f"Number of events marked done: {number_of_events_marked_done}")
                # LOGGER.info(f"Remaining items in queue: {remaining_items}")
            except Exception as e:
                LOGGER.error(f"Unhandled exception in process_events: {e}")
                LOGGER.error(traceback.format_exc())
                await asyncio.sleep(5)  # Wait a bit before retrying

    async def async_write_to_mongo_db(self, events):
        if len(events) > 0:
            try:
                result = await ASYNC_MONGO_DB.events.insert_many(events, ordered=False)
                # LOGGER.info(
                #    f"Finished writing events to db with result: {len(result.inserted_ids)}"
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

    async def process_single_neo4j_query(self):
        async with self.neo4j_semaphore:
            try:
                query = await self.neo4j_queue.get()
                async with NEO4J_DRIVER.session() as session:
                    try:
                        # LOGGER.debug(
                        #     f"Executing query: {query['query']} with params: {query['params']}"
                        # )
                        result = await session.run(query["query"], **query["params"])
                        await asyncio.sleep(0.001)
                    except Exception as e:
                        LOGGER.error(f"Error executing query in Neo4j: {str(e)}")
                        LOGGER.error(
                            f"Failed query: {query['query'][:100]}... Params: {query['params']}"
                        )
                        traceback.print_exc()
                    finally:
                        self.neo4j_queue.task_done()
            except Exception as e:
                LOGGER.error(f"Unhandled exception in process_neo4j_queries: {e}")
                traceback.print_exc()
                await asyncio.sleep(2)  # Wait a bit before retrying

    async def process_neo4j_queries(self):
        while True:
            await self.process_single_neo4j_query()

    async def create_neo4j_queries(self, events):
        if not events:
            return

        for event in events:
            # Step 1: figure out what additional labels this event will get
            additional_event_labels = []
            additional_properties = {}
            if 5000 <= event["kind"] < 6000:
                additional_event_labels = ["DVMRequest"]
                if "tags" in event:
                    for tag in event["tags"]:
                        if len(tag) > 0 and tag[0] == "encrypted":
                            additional_event_labels.append("Encrypted")

            elif 6000 <= event["kind"] < 6999:
                additional_event_labels = ["DVMResult"]
                if "tags" in event:
                    for tag in event["tags"]:
                        if len(tag) > 0 and tag[0] == "encrypted":
                            additional_event_labels.append("Encrypted")
            elif event["kind"] == 7000:
                # print("event is kind 7000")
                additional_event_labels.append("Feedback")
                # check the tags
                if "tags" in event:
                    # tags = ast.literal_eval(event["tags"])
                    tags = event["tags"]
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

                        if len(tag) > 0 and tag[0] == "encrypted":
                            additional_event_labels.append("Encrypted")

            # now create the event
            if len(additional_event_labels) == 0:
                # do nothing for now
                pass

            event_query = (
                """
                    OPTIONAL MATCH (existing:Event"""
                + ":".join(additional_event_labels)
                + """ {id: $event_id})
                    WITH existing
                    WHERE existing IS NULL
                    CREATE (n:Event:"""
                + ":".join(additional_event_labels)
                + """{id: $event_id}) 
                    SET n += apoc.convert.fromJsonMap($json)
                    RETURN n
                """
            )

            # else:
            #     pass
            #     # LOGGER.warning(f"No additional labels for event: {event}")
            #     # event_query = """
            #     #             OPTIONAL MATCH (existing:Event {id: $event_id})
            #     #             WITH existing
            #     #             WHERE existing IS NULL
            #     #             CREATE (n:Event {id: $event_id})
            #     #                         SET n = apoc.convert.fromJsonMap($json)
            #     #                         RETURN n
            #     #                     """
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
                "params": {
                    "event_id": event["id"],
                    "json": json.dumps(sanitize_json(event)),
                },
            }
            # LOGGER.info(
            #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_event_query)}"
            # )
            await self.neo4j_queue.put(ready_to_execute_event_query)

            # Step 3: Determine what other nodes and relations to also submit based on additional_event_labels
            if additional_event_labels == ["DVMRequest"]:
                # if this is a DVMRequest, then we need (1) a User Node and (2) a MADE_EVENT relation
                user_node_query = """
                    OPTIONAL MATCH (existing:User {npub_hex: $npub_hex})
                    WITH existing
                    WHERE existing IS NULL
                    CREATE (n:User {npub_hex: $npub_hex})
                    SET n += apoc.convert.fromJsonMap($json)
                    RETURN n
                """

                user_npub = hex_to_npub(event["pubkey"])
                user_node_query_params = {
                    "npub_hex": event["pubkey"],
                    "json": json.dumps(
                        {
                            "npub": user_npub,
                            "url": "https://dvmdash.live/npub/" + user_npub,
                            "neo4j_node_type": "User",
                        }
                    ),
                }

                # TODO - later we can submit a request to relays to get a kind 0 profile for the USER and add
                #  these values to the params

                ready_to_execute_user_query = {
                    "query": user_node_query,
                    "params": user_node_query_params,
                }
                LOGGER.info(
                    f"ready to execute query:\n{format_query_with_params(ready_to_execute_user_query)}"
                )
                await self.neo4j_queue.put(ready_to_execute_user_query)

                # now do the MADE_EVENT relation
                made_event_query = """
                    MATCH (n:User {npub_hex: $npub_hex})
                    MATCH (r:Event:DVMRequest {id: $event_id})
                    WHERE NOT (n)-[:MADE_EVENT]->(r)
                    CREATE (n)-[rel:MADE_EVENT]->(r)
                    RETURN rel
                """

                ready_to_execute_made_event_query = {
                    "query": made_event_query,
                    "params": {
                        "npub_hex": event["pubkey"],
                        "event_id": event["id"],
                    },
                }
                LOGGER.info(
                    f"ready to execute query:\n{format_query_with_params(ready_to_execute_made_event_query)}"
                )
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
                        OPTIONAL MATCH (existing:DVM {npub_hex: $npub_hex})
                        WITH existing
                        WHERE existing IS NULL
                        CREATE (n:DVM {npub_hex: $npub_hex})
                        SET n += apoc.convert.fromJsonMap($json)
                        RETURN n
                    """

                    dvm_npub = hex_to_npub(event["pubkey"])
                    dvm_node_query_params = {
                        "npub_hex": event["pubkey"],
                        "json": json.dumps(
                            {
                                "npub": dvm_npub,
                                "url": "https://dvmdash.live/dvm/" + dvm_npub,
                                "neo4j_node_type": "DVM",
                            }
                        ),
                    }

                    # TODO - later we can submit a request to relays to get a kind 31990 profile for the DVM and add
                    #  these values to the dvm node params

                    ready_to_execute_dvm_node_query = {
                        "query": dvm_node_query,
                        "params": dvm_node_query_params,
                    }
                    # LOGGER.info(
                    #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_dvm_node_query)}"
                    # )
                    await self.neo4j_queue.put(ready_to_execute_dvm_node_query)

                    # now create the MADE_EVENT relation query

                    dvm_made_event_query = """
                        MATCH (n:DVM {npub_hex: $npub_hex})
                        MATCH (r:Event:DVMResult {id: $event_id})
                        WHERE NOT (n)-[:MADE_EVENT]->(r)
                        CREATE (n)-[rel:MADE_EVENT]->(r)
                        RETURN rel
                    """

                    ready_to_execute_dvm_made_event_query = {
                        "query": dvm_made_event_query,
                        "params": {
                            "npub_hex": event["pubkey"],
                            "event_id": event["id"],
                        },
                    }
                    # LOGGER.info(
                    #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_dvm_made_event_query)}"
                    # )
                    await self.neo4j_queue.put(ready_to_execute_dvm_made_event_query)

                    # now because this is a DVMResult, we want to add a relation from this to the original DVM Request

                    # now let's make the query to create that node in case it doesn't exist
                    create_dvm_request_if_not_exist_query = """
                        OPTIONAL MATCH (existing:Event:DVMResult {id: $event_id})
                        WITH existing
                        WHERE existing IS NULL
                        CREATE (n:Event:DVMResult {id: $event_id})
                        RETURN n
                    """

                    ready_to_execute_create_dvm_request_if_not_exist = {
                        "query": create_dvm_request_if_not_exist_query,
                        "params": {"event_id": dvm_request_event_id},
                    }
                    # LOGGER.info(
                    #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_create_dvm_request_if_not_exist)}"
                    # )
                    await self.neo4j_queue.put(
                        ready_to_execute_create_dvm_request_if_not_exist
                    )

                    # now make the relation from the DVMResult to the DVMRequest

                    dvm_result_to_request_relation_query = """
                        MATCH (result:Event:DVMResult {id: $result_event_id})
                        MATCH (request:Event:DVMRequest {id: $request_event_id})
                        WHERE NOT (result)-[:RESULT_FOR]->(request)
                        CREATE (result)-[rel:RESULT_FOR]->(request)
                        RETURN rel
                    """

                    ready_to_execute_dvm_result_to_request_rel_query = {
                        "query": dvm_result_to_request_relation_query,
                        "params": {
                            "result_event_id": event["id"],
                            "request_event_id": dvm_request_event_id,
                        },
                    }
                    # LOGGER.info(
                    #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_dvm_result_to_request_rel_query)}"
                    # )
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

                # create the DVM node if it doesn't exist yet
                dvm_node_query = """
                    OPTIONAL MATCH (existing:DVM {npub_hex: $npub_hex})
                    WITH existing
                    WHERE existing IS NULL
                    CREATE (n:DVM {npub_hex: $npub_hex})
                    SET n += apoc.convert.fromJsonMap($json)
                    RETURN n
                """

                dvm_npub = hex_to_npub(event["pubkey"])
                dvm_node_query_params = {
                    "npub_hex": event["pubkey"],
                    "json": json.dumps(
                        {
                            "npub": dvm_npub,
                            "url": "https://dvmdash.live/dvm/" + dvm_npub,
                            "neo4j_node_type": "DVM",
                        }
                    ),
                }

                # TODO - later we can submit a request to relays to get a kind 31990 profile for the DVM and add
                #  these values to the dvm node params

                ready_to_execute_dvm_node_query = {
                    "query": dvm_node_query,
                    "params": dvm_node_query_params,
                }
                # LOGGER.info(
                #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_dvm_node_query)}"
                # )
                await self.neo4j_queue.put(ready_to_execute_dvm_node_query)

                # create the MADE_EVENT rel from the DVM to this Feedback event
                dvm_made_feedback_query = """
                    MATCH (n:DVM {npub_hex: $npub_hex})
                    MATCH (r:Event:Feedback {id: $event_id})
                    WHERE NOT (n)-[:MADE_EVENT]->(r)
                    CREATE (n)-[rel:MADE_EVENT]->(r)
                    RETURN rel
                """

                ready_to_execute_dvm_made_feedback_query = {
                    "query": dvm_made_feedback_query,
                    "params": {"npub_hex": event["pubkey"], "event_id": event["id"]},
                }

                await self.neo4j_queue.put(ready_to_execute_dvm_made_feedback_query)

                if dvm_request_event_id:
                    # let's create an invoice node if there is one
                    if "FeedbackPaymentRequest" in additional_event_labels:
                        if "invoice_data" in additional_properties:
                            # for now we use the invoice data as a unique identifier, mostly supporting the lnbc
                            # string format
                            if not additional_properties["invoice_data"].startswith(
                                "lnbc"
                            ):
                                # TODO - add better support for other payment request types, like ecash
                                LOGGER.warning(
                                    f"invoice data for feedback event {event['id']} does not start with 'lnbc'"
                                )

                            create_invoice_node_query = """
                                OPTIONAL MATCH (existing:Invoice {id: $invoice_data})
                                WITH existing
                                WHERE existing IS NULL
                                CREATE (n:Invoice {id: $invoice_data})
                                SET n += apoc.convert.fromJsonMap($json)
                                RETURN n
                            """

                            json_inner_params = {
                                "creator_pubkey": event["pubkey"],
                                "feedback_event_id": event["id"],
                                "url": f"https://dvmdash.live/invoice/{additional_properties['invoice_data']}",
                            }

                            if "amount" in additional_properties:
                                json_inner_params["amount"] = additional_properties[
                                    "amount"
                                ]

                            invoice_params = {
                                "invoice_data": additional_properties["invoice_data"],
                                "json": json.dumps(json_inner_params),
                            }

                            ready_to_execute_create_invoice_node_query = {
                                "query": create_invoice_node_query,
                                "params": invoice_params,
                            }

                            # TODO - put this event into a mongo collection for invoices so we can display this on the webpage
                            # LOGGER.info(
                            #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_create_invoice_node_query)}"
                            # )
                            await self.neo4j_queue.put(
                                ready_to_execute_create_invoice_node_query
                            )

                            # now create a relation to this invoice from the feedback event
                            create_invoice_to_feedback_rel_query = """
                                MATCH (i:Invoice {id: $invoice_data})
                                MATCH (f:Event {id: $event_id})
                                WHERE NOT (i)-[:INVOICE_FROM]->(f)
                                CREATE (i)-[rel:INVOICE_FROM]->(f)
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
                            # LOGGER.info(
                            #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_invoice_to_feedback_rel)}"
                            # )
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
                       WHERE NOT (feedback)-[:FEEDBACK_FOR]->(request)
                       CREATE (feedback)-[rel:FEEDBACK_FOR]->(request)
                       RETURN rel
                   """

                    ready_to_execute_feedback_to_request_rel_query = {
                        "query": create_feedback_to_original_request_query,
                        "params": {
                            "feedback_event_id": event["id"],
                            "request_event_id": dvm_request_event_id,
                        },
                    }
                    # LOGGER.info(
                    #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_feedback_to_request_rel_query)}"
                    # )
                    await self.neo4j_queue.put(
                        ready_to_execute_feedback_to_request_rel_query
                    )


async def nostr_client():
    keys = Keys.generate()
    pk = keys.public_key()
    LOGGER.info(f"Nostr Test Client public key: {pk.to_bech32()}, Hex: {pk.to_hex()} ")
    signer = NostrSigner.keys(keys)
    client = Client(signer)
    for relay in RELAYS:
        await client.add_relay(relay)
    await client.connect()

    now_timestamp = Timestamp.now()
    # prev_24hr_timestamp = Timestamp.from_secs(Timestamp.now().as_secs() - 60 * 60 * 24)
    # prev_30days_timestamp = Timestamp.from_secs(
    #     Timestamp.now().as_secs() - 60 * 60 * 24 * 30
    # )

    dvm_filter = Filter().kinds(RELEVANT_KINDS).since(now_timestamp)
    await client.subscribe([dvm_filter])

    # Your existing code without the while True loop
    notification_handler = NotificationHandler()
    process_events_task = asyncio.create_task(notification_handler.process_events())
    process_neo4j_queries = asyncio.create_task(
        notification_handler.process_neo4j_queries()
    )
    await client.handle_notifications(notification_handler)
    return client, notification_handler  # Return the client for potential cleanup


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
                # if "tags" in doc_copy:
                #    doc_copy["tags"] = apoc.convert.toJson([doc_copy["tags"]])
                json_data = json.dumps(
                    doc_copy
                )  # Convert the modified document to a JSON string

                # print(
                #     f"test query is: {format_query_with_params({'query': query, '})}"
                # )

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


def global_exception_handler(loop, context):
    exception = context.get("exception", context["message"])
    LOGGER.error(f"Caught global exception: {exception}")
    LOGGER.error(traceback.format_exc())


async def test_neo4j_connection():
    async with NEO4J_DRIVER.session() as session:
        result = await session.run("CREATE (n:TestNode {name: 'test'}) RETURN n")
        data = await result.single()
        if data:
            LOGGER.info("Successfully created test node")
        else:
            LOGGER.error("Failed to create test node")


async def main():
    # await test_neo4j_connection()

    try:
        client, notification_handler = await nostr_client()

        # uncomment this to get old events from the db into neo4j
        # Fetch and process documents in batches
        # batch_size = 10  # Adjust based on your needs
        # cursor = ASYNC_MONGO_DB.events.find().batch_size(batch_size)
        #
        # async for doc in cursor:
        #     # LOGGER.info(f"doc is: {doc}")
        #     # Ensure doc is treated as a dictionary here
        #     if isinstance(doc, dict):  # Check if doc is indeed a dictionary
        #         doc.pop("_id", None)  # Safely remove '_id' if it exists
        #     else:
        #         LOGGER.warning(f"doc from DB was NOT a dict: {doc}")
        #         continue
        #
        #     # Convert document to JSON string
        #     doc_json_str = dumps(doc)
        #
        #     # Call your manual Nostr handler for each document
        #     await notification_handler.manual_insert(doc_json_str)

        # We'll create a task for client.handle_notifications, which is already running
        handle_notifications_task = asyncio.current_task()

        # Wait for all tasks to complete or for a keyboard interrupt
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        LOGGER.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        LOGGER.error(f"Unhandled exception in main: {e}")
        traceback.print_exc()
    finally:
        # Attempt to disconnect the client
        try:
            await client.disconnect()
        except Exception as e:
            LOGGER.error(f"Error disconnecting client: {e}")

        # Cancel all running tasks
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()

        # Wait for all tasks to be cancelled
        await asyncio.gather(*asyncio.all_tasks(), return_exceptions=True)

        LOGGER.info("All tasks have been cancelled, exiting...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # default is 6 hours
    parser.add_argument(
        "--runtime",
        type=int,
        help="Number of minutes to run before exiting",
        default=360,
    )
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(global_exception_handler)

    try:
        if args.runtime:
            end_time = datetime.datetime.now() + datetime.timedelta(
                minutes=args.runtime
            )
            loop.run_until_complete(
                asyncio.wait_for(main(), timeout=(args.runtime * 60))
            )
        else:
            loop.run_until_complete(main())
    except asyncio.TimeoutError:
        LOGGER.info(f"Program ran for {args.runtime} minutes and is now exiting.")
    except Exception as e:
        LOGGER.error(f"Fatal error in main loop: {e}")
        traceback.print_exc()
    finally:
        loop.close()
        LOGGER.info("Event loop closed, exiting...")
