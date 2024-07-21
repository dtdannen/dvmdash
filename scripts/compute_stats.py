import ast
import sys
from datetime import datetime, timedelta
import random
from neo4j import (
    GraphDatabase,
)
import nostr_sdk
import pymongo
from pymongo import MongoClient
import json
import os
import time
from pathlib import Path
import loguru
import dotenv
from general.dvm import EventKind
from nostr_sdk import Timestamp, LogLevel
from tqdm import tqdm
import re
from statistics import median
import traceback


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
    # connect to db
    mongo_client = MongoClient(os.getenv("MONGO_URI"))
    db = mongo_client["dvmdash"]

    try:
        result = db["events"].count_documents({})
        LOGGER.info(f"There are {result} documents in events collection")
    except Exception as e:
        LOGGER.error("Could not count documents in db")
        import traceback

        traceback.print_exc()

    LOGGER.info("Connected to cloud mongo db")

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
        LOGGER.info("Verified connectivity to local Neo4j")
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
        LOGGER.info("Verified connectivity to cloud Neo4j")

    return db, neo4j_driver


DB, NEO4J_DRIVER = setup_database()


class GlobalStats:
    dvm_requests = 0
    dvm_results = 0
    dvm_requests_24_hrs = 0
    dvm_results_24_hrs = 0
    dvm_requests_1_week = 0
    dvm_results_1_week = 0
    request_kinds_counts = {}  # key is kind, value is number of requests made by users
    result_kinds_counts = {}  # key is kind, value is number of DVM responses
    dvm_results_counts = {}  # key is dvm npub hex, value is number of times called
    dvm_nip89_profiles = {}

    @classmethod
    def compute_stats(cls):
        stats = {}
        stats["num_dvm_kinds"] = len(list(GlobalStats.request_kinds_counts.keys()))
        stats["num_dvm_feedback_kinds"] = len(list(response_kinds_counts.keys()))
        stats["zap_counts"] = zap_counts
        stats["dm_counts"] = dm_counts
        stats["uncategorized_counts"] = uncategorized_counts
        stats["num_dvm_request_kinds"] = len(
            [
                k
                for k in list(request_kinds_counts.keys())
                if k not in EventKind.get_bad_dvm_kinds()
            ]
        )
        stats["num_dvm_response_kinds"] = len(
            [
                k
                for k in list(response_kinds_counts.keys())
                if k not in EventKind.get_bad_dvm_kinds()
            ]
        )
        stats["request_kinds_counts"] = request_kinds_counts
        stats["response_kinds_counts"] = response_kinds_counts
        stats["num_dvm_request_events"] = num_dvm_request_events
        stats["num_dvm_response_events"] = num_dvm_response_events
        stats["dvm_job_results"] = {
            k: v for k, v in dvm_job_results_names.items() if v > 100
        }
        stats["dvm_pub_keys"] = len(list(dvm_job_results.keys()))
        stats["dvm_nip_89s"] = len(list(dvm_nip89_profiles.keys()))

        most_popular_dvm_npub = max(dvm_job_results, key=dvm_job_results.get)
        if (
                most_popular_dvm_npub in dvm_nip89_profiles
                and "name" in dvm_nip89_profiles[most_popular_dvm_npub]
        ):
            stats["most_popular_dvm"] = dvm_nip89_profiles[most_popular_dvm_npub]["name"]

        stats["most_popular_kind"] = max(request_kinds_counts, key=request_kinds_counts.get)





# use this class to track all stats for a given DVM
class DVM:
    instances = {}

    def __init__(self, npub_hex):
        self.npub_hex = npub_hex
        self.sats_received = []
        self.job_response_times = []

        DVM.instances[npub_hex] = self

    def add_sats_received_from_job(self, sats_received: int):
        self.sats_received.append(sats_received)

    def add_job_response_time_data_point(self, job_response_time: float):
        self.job_response_times.append(job_response_time)

    def compute_stats(self):
        stats = {
            "total_sats_received": sum(self.sats_received),
            "average_sats_received_per_job": sum(self.sats_received)
            / len(self.sats_received),
            "median_sats_received_per_job": median(self.sats_received),
            "number_jobs_completed": len(self.job_response_times),
            "average_job_response_time": sum(self.job_response_times)
            / len(self.job_response_times),
            "median_job_response_time": median(self.job_response_times),
        }

        return stats

    @classmethod
    def get_instance(cls, npub_hex):
        return cls.instances.get(npub_hex)

    @classmethod
    def get_all_stats(cls):
        return {
            npub_hex: dvm.compute_stats() for npub_hex, dvm in cls.instances.items()
        }


class Kind:
    instances = {}

    def __init__(self, kind_number: int):
        self.kind_number = kind_number
        self.total_sats_paid_to_dvms = 0
        self.job_response_times = []
        self.dvm_npubs = {}
        self.job_response_times_per_dvm = (
            {}
        )  # key is dvm, value is array of tuples (job_response_time, sats_payment)

        Kind.instances[kind_number] = self

    def add_job_done_by_dvm(
        self, dvm_npub: str, job_response_time: float, sats_received: int
    ):
        self.dvm_npubs.add(dvm_npub)
        self.job_response_times.append(job_response_time)
        if dvm_npub not in self.job_response_times_per_dvm.keys():
            self.job_response_times_per_dvm[dvm_npub] = [
                (job_response_time, sats_received)
            ]
        else:
            self.job_response_times_per_dvm[dvm_npub].append(
                (job_response_time, sats_received)
            )

        self.total_sats_paid_to_dvms += sats_received

    def compute_stats(self):
        stats = {
            "total_jobs_performed": len(self.job_response_times),
            "number_of_dvms": len(self.dvm_npubs),
            "average_job_response_time": sum(self.job_response_times)
            / len(self.job_response_times),
            "median_job_response_time": median(self.job_response_times),
            "total_sats_paid_to_dvms": self.total_sats_paid_to_dvms,
        }

        return stats

    @classmethod
    def get_instance(cls, kind_number):
        return cls.instances.get(kind_number)

    @classmethod
    def get_all_stats(cls):
        return {
            kind_number: kind.compute_stats()
            for kind_number, kind in cls.instances.items()
        }


def compute_stats():
    """
    Stats to be computed:
    - Total Number of requests
    - Total Number of responses
    - Total Number of request kinds
    - Total Number of response kinds
    - Total Number of DVM Pub Keys seen
    - Total Number of Profiles (NIP-89) seen
    - Most popular DVM - which DVM is responding the most?
    - Most popular kind
    """

    # get the number of unique kinds of all events
    all_dvm_events_cursor = DB.events.find(
        {
            "$or": [
                {
                    "kind": {
                        "$gte": 5000,
                        "$lte": 7000,
                        "$nin": EventKind.get_bad_dvm_kinds(),
                    }
                },
                {"kind": 31990},
            ]
        }
    )
    all_dvm_events = list(all_dvm_events_cursor)

    # print the memory usages of all events so far:
    memory_usage = sys.getsizeof(all_dvm_events)
    # Convert memory usage to megabytes
    memory_usage_mb = memory_usage / (1024 * 1024)
    LOGGER.info(f"Memory usage of all_dvm_events: {memory_usage_mb:.2f} MB")

    current_timestamp = Timestamp.now()
    current_secs = current_timestamp.as_secs()

    max_time_24hr = current_secs - (24 * 60 * 60)
    max_time_1week = current_secs - (7 * 24 * 60 * 60)

    for dvm_event in tqdm(all_dvm_events):
        if dvm_event["kind"] == EventKind.DVM_FEEDBACK:

        elif dvm_event["kind"] == EventKind.DVM_NIP89_ANNOUNCEMENT:
            try:
                GlobalStats.dvm_nip89_profiles[dvm_event["pubkey"]] = json.loads(
                    dvm_event["content"]
                )
            except Exception as e:
                LOGGER.error(f"Could not process NIP 89 announcement event: {dvm_event}")
        elif EventKind.DVM_REQUEST_RANGE_START <= dvm_event["kind"] <= EventKind.DVM_REQUEST_RANGE_END:
            try:
                if dvm_event["created_at"] >= max_time_1week:
                    GlobalStats.dvm_requests_1_week += 1
                    GlobalStats.dvm_requests_24_hrs += 1
                elif dvm_event["created_at"] >= max_time_24hr:
                    GlobalStats.dvm_requests_24_hrs += 1

                if dvm_event["kind"] not in GlobalStats.request_kinds_counts.keys():
                    GlobalStats.request_kinds_counts[dvm_event["kind"]] = 1
                else:
                    GlobalStats.request_kinds_counts[dvm_event["kind"]] += 1

                GlobalStats.dvm_requests += 1
            except Exception as e:
                LOGGER.error(f"Could not process dvm request event: {dvm_event}")
        elif EventKind.DVM_RESULT_RANGE_START <= dvm_event["kind"] <= EventKind.DVM_RESULT_RANGE_END:
            try:
                if dvm_event["created_at"] >= max_time_1week:
                    GlobalStats.dvm_results_1_week += 1
                    GlobalStats.dvm_results_24_hrs += 1
                elif dvm_event["created_at"] >= max_time_24hr:
                    GlobalStats.dvm_results_24_hrs += 1

                if dvm_event["kind"] not in GlobalStats.result_kinds_counts.keys():
                    GlobalStats.result_kinds_counts[dvm_event["kind"]] = 1
                else:
                    GlobalStats.result_kinds_counts[dvm_event["kind"]] += 1

                if dvm_event["kind"] not in GlobalStats.dvm_results_counts:
                    GlobalStats.dvm_results_counts[dvm_event["kind"]] = 1
                else:
                    GlobalStats.result_kinds_counts[dvm_event["kind"]] += 1

                GlobalStats.dvm_results += 1
            except Exception as e:
                LOGGER.error(f"Could not process dvm request event: {dvm_event}")

    # pub ids of all dvms
    dvm_job_results = {}

    # pub ids of all dvm requests - these are probably people?
    dvm_job_requests = {}

    for dvm_event_i in tqdm(all_dvm_events):
        if "kind" in dvm_event_i:
            kind_num = dvm_event_i["kind"]
            kind_num_as_str = str(kind_num)

            if (
                5000 <= kind_num <= 5999
                and kind_num not in EventKind.get_bad_dvm_kinds()
            ):
                num_dvm_request_events += 1
                if kind_num_as_str in request_kinds_counts:
                    request_kinds_counts[kind_num_as_str] += 1
                else:
                    request_kinds_counts[kind_num_as_str] = 1

                dvm_request_pub_key = dvm_event_i["pubkey"]
                if dvm_request_pub_key in dvm_job_requests:
                    dvm_job_requests[dvm_request_pub_key] += 1
                else:
                    dvm_job_requests[dvm_request_pub_key] = 1

            elif (
                6000 <= kind_num <= 6999
                and kind_num not in EventKind.get_bad_dvm_kinds()
            ):
                num_dvm_response_events += 1
                if kind_num_as_str in response_kinds_counts:
                    response_kinds_counts[kind_num_as_str] += 1
                else:
                    response_kinds_counts[kind_num_as_str] = 1

                dvm_pub_key = dvm_event_i["pubkey"]
                if dvm_pub_key in dvm_job_results:
                    dvm_job_results[dvm_pub_key] += 1
                else:
                    dvm_job_results[dvm_pub_key] = 1

            elif kind_num == 9735:
                zap_counts += 1
            elif kind_num == 4:
                dm_counts += 1
            else:
                uncategorized_counts += 1
        else:
            LOGGER.info("WARNING - event missing kind field")
            LOGGER.info(f"{dvm_event_i}")

    # this is used to make the bars and labels of the graphs clickable to go to the corresponding dvm page
    labels_to_pubkeys = {}

    # replace dvm_job_results keys with names if available
    dvm_job_results_names = {}
    for pub_key, count in tqdm(dvm_job_results.items()):
        if pub_key in dvm_nip89_profiles and "name" in dvm_nip89_profiles[pub_key]:
            dvm_job_results_names[dvm_nip89_profiles[pub_key]["name"]] = count
            labels_to_pubkeys[dvm_nip89_profiles[pub_key]["name"]] = pub_key
        else:
            dvm_job_results_names[pub_key[:6]] = count
            labels_to_pubkeys[pub_key[:6]] = pub_key


    # get the top 15 dvm job requests pub ids
    # first sort dictionary by value
    # then pick the top 15
    # Sort the dictionary by value in descending order and get the top 15 items
    top_dvm_job_requests = sorted(
        dvm_job_requests.items(), key=lambda x: x[1], reverse=True
    )[:15]

    # Convert the list of tuples back to a dictionary
    top_dvm_job_requests_dict = dict(top_dvm_job_requests)

    top_dvm_job_requests_via_name = {}
    for pub_key, count in top_dvm_job_requests_dict.items():
        LOGGER.info(f"pub_key: {pub_key}, count: {count}")
        if pub_key in dvm_nip89_profiles and "name" in dvm_nip89_profiles[pub_key]:
            top_dvm_job_requests_via_name[dvm_nip89_profiles[pub_key]["name"]] = count
            labels_to_pubkeys[dvm_nip89_profiles[pub_key]["name"]] = pub_key
        else:
            top_dvm_job_requests_via_name[pub_key[:6]] = count
            labels_to_pubkeys[pub_key[:6]] = pub_key

    stats["dvm_job_requests"] = top_dvm_job_requests_via_name
    stats["labels_to_pubkeys"] = json.dumps(labels_to_pubkeys).replace("'", "")

    for kind, count in request_kinds_counts.items():
        LOGGER.info(f"\tKind {kind} has {count} instances")

    LOGGER.info(f"Setting var num_dvm_kinds to {stats['num_dvm_kinds']}")

    query = {
        "kind": 7000,
        "tags": {
            "$all": [["status", "payment-required"]],
        },
    }

    payment_requests = list(DB.events.find(query))
    feedback_event_lnbc_invoice_strs = set()

    total_number_of_payments_requests = len(payment_requests)
    total_amount_millisats = 0
    average_amount_millisats = 0

    for payment_request in payment_requests:
        try:
            tags = payment_request["tags"]
            for tag in tags:
                if tag[0] == "amount":
                    total_amount_millisats += int(tag[1])

                    if len(tag) > 2 and tag[2].startswith("lnbc"):
                        feedback_event_lnbc_invoice_strs.add(tag[2])
                    break
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {payment_request['id']}: {str(e)}")
            # Skip processing tags for this record and continue with the next one

    print(
        f"There are {len(feedback_event_lnbc_invoice_strs)} invoice strs from feedback events, and one example is: "
        f"{random.choice(list(feedback_event_lnbc_invoice_strs))}"
    )

    if total_number_of_payments_requests > 0:
        average_amount_millisats = (
            total_amount_millisats / total_number_of_payments_requests
        )

    total_amount_sats = int(total_amount_millisats / 1000)
    average_amount_sats = int(average_amount_millisats / 1000)

    print(f"Total number of payment requests: {total_number_of_payments_requests}")
    print(f"Total amount (sats): {total_amount_sats}")
    print(f"Average amount (sats): {average_amount_sats}")

    stats["total_number_of_payments_requests"] = total_number_of_payments_requests
    stats["total_amount_dvm_requested_sats"] = total_amount_sats
    stats["average_amount_dvm_requested_sats"] = average_amount_sats

    # Estimate how many sats have been paid to DVMs based on them doing work after requesting payment

    total_amount_paid_millisats = 0

    neo4j_query_feedback_events = """
        MATCH (u:User)-[:MADE_EVENT]->(nr:Event:DVMRequest)
        MATCH (d:DVM)-[:MADE_EVENT]->(ns:Event:DVMResult)-[:RESULT_FOR]->(nr)
        MATCH (d:DVM)-[:MADE_EVENT]->(f:FeedbackPaymentRequest)-[:FEEDBACK_FOR]->(nr)
        RETURN f
    """

    # run the query
    with NEO4J_DRIVER.session() as session:
        result = session.run(neo4j_query_feedback_events)

        for record in result:
            feedback_event = record["f"]
            # Accessing properties (assuming 'id' and 'content' are properties of the FeedbackPaymentRequest node)
            event_id = feedback_event["id"]
            event_content = feedback_event["content"]
            tags = ast.literal_eval(feedback_event["tags"])

            # check to see the amount in the feedback event
            for tag in tags:
                if tag[0] == "amount" and len(tag) > 1:
                    total_amount_paid_millisats += int(tag[1])

    print(f"Total number of sats paid to dvms: {total_amount_paid_millisats / 1000}")

    stats["total_amount_paid_sats"] = int(total_amount_paid_millisats / 1000)

    return stats


def save_global_stats_to_mongodb(stats):
    collection_name = "global_stats"
    if collection_name not in DB.list_collection_names():
        DB.create_collection(
            collection_name,
            timeseries={
                "timeField": "timestamp",
                "metaField": "metadata",
                "granularity": "minutes",
            },
        )

    collection = DB[collection_name]

    current_time = datetime.now()
    stats_document = {"timestamp": current_time, **stats}

    collection.insert_one(stats_document)


def save_dvm_stats_to_mongodb(dvm_npub_hex, stats):
    collection_name = "dvm_stats"
    if collection_name not in DB.list_collection_names():
        DB.create_collection(
            collection_name,
            timeseries={
                "timeField": "timestamp",
                "metaField": "metadata",
                "granularity": "minutes",
            },
        )

    collection = DB[collection_name]

    current_time = datetime.now()
    stats_document = {
        "timestamp": current_time,
        "metadata": {"dvm_npub_hex": dvm_npub_hex},
        **stats,
    }

    collection.insert_one(stats_document)


def save_kind_stats_to_mongodb(kind_number, stats):
    collection_name = "kind_stats"
    if collection_name not in DB.list_collection_names():
        DB.create_collection(
            collection_name,
            timeseries={
                "timeField": "timestamp",
                "metaField": "metadata",
                "granularity": "minutes",
            },
        )

    collection = DB[collection_name]

    current_time = datetime.now()
    stats_document = {
        "timestamp": current_time,
        "metatdata": {"kind_number": kind_number},
        **stats,
    }

    collection.insert_one(stats_document)


if __name__ == "__main__":
    """Usage: python compute_stats.py"""

    try:
        LOGGER.info(f"Starting compute stats process")
        start_time = datetime.now()
        stats = compute_stats()
        save_stats_to_mongodb(stats)
        LOGGER.info(
            f"Stats computed and saved to MongoDB. Took {datetime.now() - start_time} seconds."
        )
        LOGGER.info("Goodbye!")
    except Exception as e:
        import traceback

        LOGGER.error(f"Exception occurred: {e}")
        LOGGER.error(traceback.format_exc())
        LOGGER.info("Goodbye!")
