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
    dvm_nip89_profiles = {}  #
    user_request_counts = (
        {}
    )  # key is the users npub, value is number of dvm requests they've made
    total_number_of_payments_requests = 0
    total_amount_millisats = 0
    total_amount_paid_to_dvm_millisats = 0

    @classmethod
    def compute_stats(cls):
        stats = {
            "dvm_requests_all_time": GlobalStats.dvm_requests,
            "dvm_results_all_time": GlobalStats.dvm_results,
            "dvm_requests_24_hrs": GlobalStats.dvm_requests_24_hrs,
            "dvm_results_24_hrs": GlobalStats.dvm_results_24_hrs,
            "dvm_requests_1_week": GlobalStats.dvm_requests_1_week,
            "dvm_results_1_week": GlobalStats.dvm_results_1_week,
            "num_dvm_request_kinds": len(GlobalStats.request_kinds_counts.keys()),
            "num_dvm_response_kinds": len(GlobalStats.result_kinds_counts.keys()),
            "dvm_nip_89s": len(GlobalStats.dvm_nip89_profiles.keys()),
            "dvm_pub_keys": len(GlobalStats.dvm_results_counts.keys()),
            "total_number_of_payments_requests": GlobalStats.total_number_of_payments_requests,
            "total_amount_dvm_requested_sats": int(
                GlobalStats.total_amount_millisats / 1000
            ),
            "total_amount_paid_to_dvm_sats": int(
                GlobalStats.total_amount_paid_to_dvm_millisats / 1000
            ),
        }

        most_popular_dvm_npub = max(
            GlobalStats.dvm_results_counts, key=GlobalStats.dvm_results_counts.get
        )
        if (
            most_popular_dvm_npub in GlobalStats.dvm_nip89_profiles
            and "name" in GlobalStats.dvm_nip89_profiles[most_popular_dvm_npub]
        ):
            stats["most_popular_dvm_name"] = GlobalStats.dvm_nip89_profiles[
                most_popular_dvm_npub
            ]["name"]
        else:
            stats[
                "most_popular_dvm_name"
            ] = f"{most_popular_dvm_npub[:8]}...{most_popular_dvm_npub[:-4]}"

        stats[
            "most_popular_dvm_npub"
        ] = most_popular_dvm_npub  # this is to make the metric clickable
        stats["most_popular_kind"] = max(
            GlobalStats.request_kinds_counts, key=GlobalStats.request_kinds_counts.get
        )
        stats["unique_users_of_dvms"] = len(GlobalStats.user_request_counts.keys())
        return stats


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


def compute_all_stats():
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
        if dvm_event["kind"] == EventKind.DVM_FEEDBACK.value:
            try:
                has_payment_required = False
                payment_amount = 0
                for tag in dvm_event["tags"]:
                    if (
                        tag[0] == "status"
                        and len(tag) > 1
                        and tag[1] == "payment-required"
                    ):
                        has_payment_required = True
                    elif tag[0] == "amount" and len(tag) > 1:
                        payment_amount = int(tag[1])
                if has_payment_required:
                    GlobalStats.total_number_of_payments_requests += 1
                    GlobalStats.total_amount_millisats += payment_amount
            except Exception as e:
                LOGGER.error(f"Could not process feedback event {dvm_event}: {e}")
        elif dvm_event["kind"] == EventKind.DVM_NIP89_ANNOUNCEMENT.value:
            try:
                GlobalStats.dvm_nip89_profiles[dvm_event["pubkey"]] = json.loads(
                    dvm_event["content"]
                )
            except Exception as e:
                LOGGER.error(
                    f"Could not process NIP 89 announcement event {dvm_event}: {e}"
                )
        elif (
            EventKind.DVM_REQUEST_RANGE_START.value
            <= dvm_event["kind"]
            <= EventKind.DVM_REQUEST_RANGE_END.value
        ):
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

                if dvm_event["pubkey"] not in GlobalStats.user_request_counts.keys():
                    GlobalStats.user_request_counts[dvm_event["pubkey"]] = 1
                else:
                    GlobalStats.user_request_counts[dvm_event["pubkey"]] += 1

                GlobalStats.dvm_requests += 1
            except Exception as e:
                LOGGER.error(f"Could not process dvm request event {dvm_event}: {e}")
        elif (
            EventKind.DVM_RESULT_RANGE_START.value
            <= dvm_event["kind"]
            <= EventKind.DVM_RESULT_RANGE_END.value
        ):
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

                if dvm_event["pubkey"] not in GlobalStats.dvm_results_counts:
                    GlobalStats.dvm_results_counts[dvm_event["pubkey"]] = 1
                else:
                    GlobalStats.dvm_results_counts[dvm_event["pubkey"]] += 1

                GlobalStats.dvm_results += 1
            except Exception as e:
                LOGGER.error(f"Could not process dvm request event {dvm_event}: {e}")

    # Estimate how many sats have been paid to DVMs based on them doing work after requesting payment
    def process_feedback_event(feedback_event):
        print("Processing feedback event: {}".format(feedback_event))
        tags = feedback_event.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = ast.literal_eval(tags)
            except (ValueError, SyntaxError) as e:
                LOGGER.error(f"Failed to parse tags: {e}")
                return

        for tag in tags:
            print(f"tag is: {tag}")
            if tag[0] == "amount" and len(tag) > 1:
                try:
                    amount = int(tag[1])
                    GlobalStats.total_amount_paid_to_dvm_millisats += amount
                except ValueError as e:
                    LOGGER.error(f"Invalid amount value: {tag[1]}, Error: {e}")

    neo4j_query_feedback_events = """
            MATCH (u:User)-[:MADE_EVENT]->(nr:Event:DVMRequest)
            MATCH (d:DVM)-[:MADE_EVENT]->(ns:Event:DVMResult)-[:RESULT_FOR]->(nr)
            MATCH (d:DVM)-[:MADE_EVENT]->(f:FeedbackPaymentRequest)-[:FEEDBACK_FOR]->(nr)
            RETURN f
        """

    with NEO4J_DRIVER.session() as session:
        try:
            result = session.execute_read(
                lambda tx: list(tx.run(neo4j_query_feedback_events))
            )

            for record in result:
                feedback_event = record.get("f")
                if feedback_event:
                    process_feedback_event(feedback_event)
                else:
                    LOGGER.warning("Record missing 'f' key")
        except Exception as e:
            LOGGER.error(f"Failed to execute Neo4j query: {e}")


def save_global_stats_to_mongodb():
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
    stats = GlobalStats.compute_stats()
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
        compute_all_stats()
        save_global_stats_to_mongodb()
        LOGGER.info(
            f"Stats computed and saved to MongoDB. Took {datetime.now() - start_time} seconds."
        )
        LOGGER.info("Goodbye!")
    except Exception as e:
        import traceback

        LOGGER.error(f"Exception occurred: {e}")
        LOGGER.error(traceback.format_exc())
        LOGGER.info("Goodbye!")
