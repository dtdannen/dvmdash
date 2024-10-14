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
from neo4j import AsyncGraphDatabase, GraphDatabase
import motor.motor_asyncio
import pymongo  # used only to create new collections if they don't exist
from pymongo.errors import BulkWriteError, InvalidOperation
from shared.dvm import EventKind
from shared.helpers import hex_to_npub, sanitize_json, format_query_with_params
import traceback
import argparse
import datetime

# import dumps from bson
from bson.json_util import dumps
from bson import ObjectId
from tqdm import tqdm


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


def create_neo4j_queries(event):
    neo4j_queries_in_order = []

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
                if len(tag) > 1 and tag[0] == "status" and tag[1] == "payment-required":
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
        LOGGER.debug(
            f"skipping event kind {event['kind']} because no additional labels"
        )
        return []

    # new
    labels = ":".join(["Event"] + additional_event_labels)
    event_query = f"""
                    MERGE (n:{labels} {{id: $event_id}})
                    ON CREATE SET n += apoc.convert.fromJsonMap($json)
                    ON MATCH SET n += apoc.convert.fromJsonMap($json)
                    RETURN n
                """

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
    neo4j_queries_in_order.append(ready_to_execute_event_query)

    # Step 3: Determine what other nodes and relations to also submit based on additional_event_labels
    if additional_event_labels == ["DVMRequest"]:
        # if this is a DVMRequest, then we need (1) a User Node and (2) a MADE_EVENT relation
        user_node_query = """
                            MERGE (n:User {npub_hex: $npub_hex})
                            ON CREATE SET n += apoc.convert.fromJsonMap($json)
                            ON MATCH SET n += apoc.convert.fromJsonMap($json)
                            RETURN n
                        """

        user_npub = hex_to_npub(event["pubkey"])
        user_node_query_params = {
            "npub_hex": event["pubkey"],
            "json": json.dumps(
                sanitize_json(
                    {
                        "npub": user_npub,
                        "url": "https://dvmdash.live/npub/" + user_npub,
                        "neo4j_node_type": "User",
                    }
                )
            ),
        }

        # TODO - later we can submit a request to relays to get a kind 0 profile for the USER and add
        #  these values to the params

        ready_to_execute_user_query = {
            "query": user_node_query,
            "params": user_node_query_params,
        }
        # LOGGER.info(
        #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_user_query)}"
        # )
        neo4j_queries_in_order.append(ready_to_execute_user_query)

        # now do the MADE_EVENT relation
        made_event_query = """
                            MATCH (n:User {npub_hex: $npub_hex})
                            MATCH (r:Event:DVMRequest {id: $event_id})
                            MERGE (n)-[rel:MADE_EVENT]->(r)
                            ON CREATE SET rel.created_at = timestamp()
                            ON MATCH SET rel.updated_at = timestamp()
                            RETURN rel
                        """

        ready_to_execute_made_event_query = {
            "query": made_event_query,
            "params": {
                "npub_hex": event["pubkey"],
                "event_id": event["id"],
            },
        }
        # LOGGER.info(
        #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_made_event_query)}"
        # )
        neo4j_queries_in_order.append(ready_to_execute_made_event_query)
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
                                    SET n += apoc.convert.fromJsonMap($json)
                                    RETURN n
                                """

            dvm_npub = hex_to_npub(event["pubkey"])
            dvm_node_query_params = {
                "npub_hex": event["pubkey"],
                "json": json.dumps(
                    sanitize_json(
                        {
                            "npub": dvm_npub,
                            "url": "https://dvmdash.live/dvm/" + dvm_npub,
                            "neo4j_node_type": "DVM",
                        }
                    )
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
            neo4j_queries_in_order.append(ready_to_execute_dvm_node_query)

            # now create the MADE_EVENT relation query

            dvm_made_event_query = """
                                    MATCH (n:DVM {npub_hex: $npub_hex})
                                    MATCH (r:Event:DVMResult {id: $event_id})
                                    MERGE (n)-[rel:MADE_EVENT]->(r)
                                    ON CREATE SET rel.created_at = timestamp()
                                    ON MATCH SET rel.updated_at = timestamp()
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
            neo4j_queries_in_order.append(ready_to_execute_dvm_made_event_query)

            # now because this is a DVMResult, we want to add a relation from this to the original DVM Request

            # now let's make the query to create that node in case it doesn't exist
            create_dvm_request_query = """
                                    MERGE (n:Event:DVMRequest {id: $event_id})
                                    ON CREATE SET n += apoc.convert.fromJsonMap($json)
                                    ON MATCH SET n += apoc.convert.fromJsonMap($json)
                                    RETURN n
                                """

            ready_to_execute_create_dvm_request_if_not_exist = {
                "query": create_dvm_request_query,
                "params": {"event_id": dvm_request_event_id, "json": json.dumps({})},
            }
            # LOGGER.info(
            #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_create_dvm_request_if_not_exist)}"
            # )
            neo4j_queries_in_order.append(
                ready_to_execute_create_dvm_request_if_not_exist
            )

            # now make the relation from the DVMResult to the DVMRequest

            dvm_result_to_request_relation_query = """
                                    MATCH (result:Event:DVMResult {id: $result_event_id})
                                    MATCH (request:Event:DVMRequest {id: $request_event_id})
                                    MERGE (result)-[rel:RESULT_FOR]->(request)
                                    ON CREATE SET rel.created_at = timestamp()
                                    ON MATCH SET rel.updated_at = timestamp()
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
            neo4j_queries_in_order.append(
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
                            MERGE (n:DVM {npub_hex: $npub_hex})
                            ON CREATE SET n += apoc.convert.fromJsonMap($json)
                            ON MATCH SET n += apoc.convert.fromJsonMap($json)
                            RETURN n
                        """

        dvm_npub = hex_to_npub(event["pubkey"])
        dvm_node_query_params = {
            "npub_hex": event["pubkey"],
            "json": json.dumps(
                sanitize_json(
                    {
                        "npub": dvm_npub,
                        "url": "https://dvmdash.live/dvm/" + dvm_npub,
                        "neo4j_node_type": "DVM",
                    }
                )
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
        neo4j_queries_in_order.append(ready_to_execute_dvm_node_query)

        # create the MADE_EVENT rel from the DVM to this Feedback event
        dvm_made_feedback_query = """
                            MATCH (n:DVM {npub_hex: $npub_hex})
                            MATCH (r:Event:Feedback {id: $event_id})
                            MERGE (n)-[rel:MADE_EVENT]->(r)
                            ON CREATE SET rel.created_at = timestamp()
                            ON MATCH SET rel.updated_at = timestamp()
                            RETURN rel
                        """

        ready_to_execute_dvm_made_feedback_query = {
            "query": dvm_made_feedback_query,
            "params": {"npub_hex": event["pubkey"], "event_id": event["id"]},
        }

        neo4j_queries_in_order.append(ready_to_execute_dvm_made_feedback_query)

        if dvm_request_event_id:
            # let's create an invoice node if there is one
            if "FeedbackPaymentRequest" in additional_event_labels:
                if "invoice_data" in additional_properties:
                    # for now we use the invoice data as a unique identifier, mostly supporting the lnbc
                    # string format
                    if not additional_properties["invoice_data"].startswith("lnbc"):
                        # TODO - add better support for other payment request types, like ecash
                        LOGGER.warning(
                            f"invoice data for feedback event {event['id']} does not start with 'lnbc'"
                        )

                    create_invoice_node_query = """
                                                    MERGE (n:Invoice {id: $invoice_data})
                                                    ON CREATE SET n += apoc.convert.fromJsonMap($json)
                                                    ON MATCH SET n += apoc.convert.fromJsonMap($json)
                                                    RETURN n
                                                """

                    json_inner_params = {
                        "creator_pubkey": event["pubkey"],
                        "feedback_event_id": event["id"],
                        "url": f"https://dvmdash.live/invoice/{additional_properties['invoice_data']}",
                        "node_type": "Invoice",
                    }

                    if "amount" in additional_properties:
                        json_inner_params["amount"] = additional_properties["amount"]

                    invoice_params = {
                        "invoice_data": additional_properties["invoice_data"],
                        "json": json.dumps(sanitize_json(json_inner_params)),
                    }

                    ready_to_execute_create_invoice_node_query = {
                        "query": create_invoice_node_query,
                        "params": invoice_params,
                    }

                    # TODO - put this event into a mongo collection for invoices so we can display this on the webpage
                    # LOGGER.info(
                    #     f"ready to execute query:\n{format_query_with_params(ready_to_execute_create_invoice_node_query)}"
                    # )
                    neo4j_queries_in_order.append(
                        ready_to_execute_create_invoice_node_query
                    )

                    # now create a relation to this invoice from the feedback event
                    create_invoice_to_feedback_rel_query = """
                                                    MATCH (i:Invoice {id: $invoice_data})
                                                    MATCH (f:Event {id: $event_id})
                                                    MERGE (i)-[rel:INVOICE_FROM]->(f)
                                                    ON CREATE SET rel.created_at = timestamp()
                                                    ON MATCH SET rel.updated_at = timestamp()
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
                    neo4j_queries_in_order.append(
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
                                    ON CREATE SET rel.created_at = timestamp()
                                    ON MATCH SET rel.updated_at = timestamp()
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
            neo4j_queries_in_order.append(
                ready_to_execute_feedback_to_request_rel_query
            )

    return neo4j_queries_in_order


BATCH_SIZE = 500


def execute_bulk_queries(tx, queries):
    for query in queries:
        tx.run(query["query"], query["params"])


def process_batch(session, batch):
    all_queries_in_order = (
        {}
    )  # key is a number meaning the location in place of the original query
    neo4j_processed_count = 0
    for event in batch:
        event_queries = create_neo4j_queries(event)
        for i, query in enumerate(event_queries):
            if i not in all_queries_in_order.keys():
                all_queries_in_order[i] = [query]
            else:
                all_queries_in_order[i].append(query)

    for i in range(len(all_queries_in_order.keys())):
        print(f"all_queries_in_order[{i}]: {len(all_queries_in_order[i])}")

    # the following loop must run in order of the keys of all_queries
    # this prevents neo4j queries from missing dependencies
    for i in range(len(all_queries_in_order.keys())):
        transaction_queries = all_queries_in_order[i]
        len_of_queries = len(transaction_queries)
        session.execute_write(execute_bulk_queries, transaction_queries)
        print(f"wrote {len_of_queries} to neo4j")
        neo4j_processed_count += len_of_queries

    return neo4j_processed_count


def process_mongo_to_neo4j():
    # Connect to new mongo db
    sync_db_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
    sync_db = sync_db_client["dvmdash"]

    URI = os.getenv("NEO4J_URI")
    AUTH = (os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))

    # connect to neo4j
    neo4j_driver = GraphDatabase.driver(
        URI,
        auth=AUTH,
    )

    total_documents = sync_db.prod_events.count_documents({})

    # this is used to recover from failures in the middle
    # SKIP_AHEAD = 0
    SKIP_AHEAD = 89000

    for skip in range(SKIP_AHEAD, total_documents, BATCH_SIZE):
        batch = list(sync_db.prod_events.find().skip(skip).limit(BATCH_SIZE))

        with neo4j_driver.session() as session:
            neo4j_processed_count = process_batch(session, batch)

        processed_count = skip + len(batch)
        percentage_complete = (processed_count / total_documents) * 100
        print(
            f"Processed batch: {skip} to {processed_count} ({percentage_complete:.2f}% complete),"
            f" number of neo4j queries processed is {neo4j_processed_count}"
        )

    sync_db_client.close()
    neo4j_driver.close()


if __name__ == "__main__":
    process_mongo_to_neo4j()
