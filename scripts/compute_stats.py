import ast
import sys
from datetime import datetime, timedelta
import random
from neo4j import (
    GraphDatabase,
)
import nostr_sdk
import pymongo
from pymongo import MongoClient, InsertOne
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
        self.nip_89_profile = None
        self.profile_created_at = None

        DVM.instances[npub_hex] = self

    def add_sats_received_from_job(self, sats_received: int):
        self.sats_received.append(sats_received)

    def add_job_response_time_data_point(self, job_response_time: float):
        self.job_response_times.append(job_response_time)

    def add_nip89_profile(self, profile, created_at):
        if (
            self.nip_89_profile
            and self.profile_created_at
            and self.profile_created_at > created_at
        ):
            # do nothing because we already have a more recent nip89 profile
            return

        self.nip_89_profile = profile
        self.profile_created_at = created_at

    def compute_stats(self):
        stats = {
            "total_sats_received": int(sum(self.sats_received)),
            "number_jobs_completed": len(self.job_response_times),
        }

        if stats["total_sats_received"] > 0:
            stats["total_sats_received"] = int(sum(self.sats_received) / 1000)
            stats["average_sats_received_per_job"] = int(
                (sum(self.sats_received) / len(self.sats_received)) / 1000
            )
            stats["median_sats_received_per_job"] = median(self.sats_received) / 1000
        else:
            stats["total_sats_received"] = 0
            stats["average_sats_received_per_job"] = -1
            stats["median_sats_received_per_job"] = -1

        if stats["number_jobs_completed"] > 0:
            stats["average_job_response_time"] = int(
                sum(self.job_response_times) / len(self.job_response_times)
            )
            stats["median_job_response_time"] = median(self.job_response_times)
        else:
            stats["average_job_response_time"] = -1
            stats["median_job_response_time"] = -1

        if self.nip_89_profile:
            stats["profile"] = self.nip_89_profile

        return stats

    @classmethod
    def get_instance(cls, npub_hex):
        if npub_hex not in cls.instances:
            cls.instances[npub_hex] = cls(npub_hex)
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
        self.job_requests = 0
        self.job_response_times = []
        self.job_response_times_per_dvm = (
            {}
        )  # key is dvm npub hex, value is array of tuples (job_response_time, sats_payment)

        Kind.instances[kind_number] = self

    def add_job_done_by_dvm(
        self, dvm_npub: str, job_response_time: float, sats_received: int
    ):
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
        # first compute the average response time of each dvm
        avg_data_per_dvm = (
            {}
        )  # key is dvm npub hex, value is a single tuple containing avg and median response time and payment
        for dvm_npub_hex, data in self.job_response_times_per_dvm.items():
            response_times, sats_received_values = [], []
            for job_response_time, sats_received in data:
                response_times.append(job_response_time)
                sats_received_values.append(sats_received)

            avg_data_per_dvm[dvm_npub_hex] = {}

            # calculate the average and median
            avg_data_per_dvm[dvm_npub_hex]["avg_response_time"] = int(
                sum(response_times) / len(data)
            )
            avg_data_per_dvm[dvm_npub_hex]["avg_sats_received"] = int(
                (sum(sats_received_values) / 1000) / len(data)
            )
            avg_data_per_dvm[dvm_npub_hex]["median_response_time"] = int(
                median(response_times)
            )
            avg_data_per_dvm[dvm_npub_hex]["median_sats_received"] = int(
                median(sats_received_values) / 1000
            )

        stats = {
            "total_jobs_requested": self.job_requests,
            "total_jobs_performed": len(self.job_response_times),
            "number_of_dvms": len(list(avg_data_per_dvm.keys())),
            "total_sats_paid_to_dvms": int(self.total_sats_paid_to_dvms / 1000),
            "dvm_npubs": list(avg_data_per_dvm.keys()),
            "data_per_dvm": avg_data_per_dvm,
        }

        if stats["total_jobs_performed"] > 0:
            stats["average_job_response_time"] = int(
                sum(self.job_response_times) / len(self.job_response_times)
            )
            stats["median_job_response_time"] = int(median(self.job_response_times))
        else:
            stats["average_job_response_time"] = -1
            stats["median_job_response_time"] = -1

        return stats

    @classmethod
    def get_instance(cls, kind_number):
        # we will use the request kind number for all data related to the request and the result
        if (
            EventKind.DVM_RESULT_RANGE_START.value
            <= kind_number
            <= EventKind.DVM_RESULT_RANGE_END.value
        ):
            kind_number = kind_number - 1000  # this gives us the request kind number
        if kind_number not in cls.instances:
            cls.instances[kind_number] = cls(kind_number)
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
                LOGGER.debug(f"Could not process feedback event {dvm_event}: {e}")
        elif dvm_event["kind"] == EventKind.DVM_NIP89_ANNOUNCEMENT.value:
            try:
                if "content" in dvm_event and len(dvm_event["content"]) > 0:
                    nip89_profile = json.loads(dvm_event["content"])
                    GlobalStats.dvm_nip89_profiles[dvm_event["pubkey"]] = nip89_profile
                    DVM.get_instance(dvm_event["pubkey"]).add_nip89_profile(
                        nip89_profile, dvm_event["created_at"]
                    )
            except Exception as e:
                LOGGER.debug(
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

                Kind.get_instance(dvm_event["kind"]).job_requests += 1

                GlobalStats.dvm_requests += 1
            except Exception as e:
                LOGGER.debug(f"Could not process dvm request event {dvm_event}: {e}")
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
                LOGGER.debug(f"Could not process dvm request event {dvm_event}: {e}")

    # Estimate how many sats have been paid to DVMs based on them doing work after requesting payment
    def process_feedback_event(feedback_event, dvm_node, response_event, result_event):
        feedback_tags = feedback_event.get("tags", [])
        if isinstance(feedback_tags, str):
            try:
                feedback_tags = ast.literal_eval(feedback_tags)
            except (ValueError, SyntaxError) as e:
                LOGGER.error(f"Failed to parse tags: {e}")
                return

        dvm_npub_hex = dvm_node.get(
            "npub_hex"
        )  # Assuming the DVM node has an 'npub' property
        dvm_instance = DVM.get_instance(dvm_npub_hex)
        request_created_at = response_event.get("created_at")
        result_created_at = result_event.get("created_at")
        kind_number = result_event.get("kind")

        response_time_secs = None
        if request_created_at and result_created_at:
            # calculate the response time for the job to be done
            response_time_secs = result_created_at - request_created_at
            dvm_instance.add_job_response_time_data_point(response_time_secs)

        for tag in feedback_tags:
            if tag[0] == "amount" and len(tag) > 1:
                try:
                    amount = int(tag[1])
                    GlobalStats.total_amount_paid_to_dvm_millisats += amount
                    dvm_instance.add_sats_received_from_job(amount)
                    if response_time_secs is None:
                        raise Exception(
                            f"response time is missing for kind {kind_number}."
                        )
                    Kind.get_instance(kind_number).add_job_done_by_dvm(
                        dvm_npub_hex, response_time_secs, amount
                    )
                except ValueError as e:
                    LOGGER.error(f"Invalid amount value: {tag[1]}, Error: {e}")
                except Exception as e:
                    LOGGER.error(f"Error processing neo4j feedback event: {e}")

    neo4j_query_feedback_events = """
            MATCH (u:User)-[:MADE_EVENT]->(nr:Event:DVMRequest)
            MATCH (d:DVM)-[:MADE_EVENT]->(ns:Event:DVMResult)-[:RESULT_FOR]->(nr)
            MATCH (d:DVM)-[:MADE_EVENT]->(f:FeedbackPaymentRequest)-[:FEEDBACK_FOR]->(nr)
            RETURN f, d, nr, ns
        """

    with NEO4J_DRIVER.session() as session:
        try:
            result = session.execute_read(
                lambda tx: list(tx.run(neo4j_query_feedback_events))
            )

            for record in result:
                feedback_event = record.get("f")
                dvm_node = record.get("d")
                request_event = record.get("nr")
                result_event = record.get("ns")
                if feedback_event and dvm_node and request_event and result_event:
                    process_feedback_event(
                        feedback_event, dvm_node, request_event, result_event
                    )
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


def save_dvm_stats_to_mongodb():
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
    bulk_operations = []

    for dvm in DVM.instances.values():
        stats = dvm.compute_stats()
        stats_document = {
            "timestamp": current_time,
            "metadata": {"dvm_npub_hex": dvm.npub_hex},
            **stats,
        }
        bulk_operations.append(InsertOne(stats_document))

    if bulk_operations:
        result = collection.bulk_write(bulk_operations)
        print(f"Inserted {result.inserted_count} DVM stat documents")
    else:
        print("No DVM stats to insert")


def save_kind_stats_to_mongodb():
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
    bulk_operations = []
    for kind in Kind.instances.values():
        stats = kind.compute_stats()
        stats_document = {
            "timestamp": current_time,
            "metadata": {"kind_number": kind.kind_number},
            **stats,
        }
        bulk_operations.append(InsertOne(stats_document))

    if bulk_operations:
        result = collection.bulk_write(bulk_operations)
        print(f"Inserted {result.inserted_count} KIND stat documents")
    else:
        print("No KIND stats to insert")


def global_stats_via_big_mongo_query():
    stats = {}

    current_timestamp = int(time.time())
    max_time_24hr = current_timestamp - (24 * 60 * 60)
    max_time_1week = current_timestamp - (7 * 24 * 60 * 60)
    max_time_1month = current_timestamp - (30 * 24 * 60 * 60)

    pipeline = [
        {
            "$match": {
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
        },
        {
            "$facet": {
                "event_counts": [
                    {"$group": {"_id": "$kind", "count": {"$sum": 1}}},
                    {
                        "$project": {
                            "_id": 0,  # Exclude the _id field
                            "kind": "$_id",  # Rename _id to kind
                            "count": 1,  # Include the count field
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "details": {"$push": "$$ROOT"},
                            "sum_5000_5999": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$and": [
                                                {"$gte": ["$kind", 5000]},
                                                {"$lte": ["$kind", 5999]},
                                            ]
                                        },
                                        "$count",
                                        0,
                                    ]
                                }
                            },
                            "sum_6000_6999": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$and": [
                                                {"$gte": ["$kind", 6000]},
                                                {"$lte": ["$kind", 6999]},
                                            ]
                                        },
                                        "$count",
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                    {
                        "$project": {
                            "details": 1,
                            "range_sums": {
                                "5000_5999": "$sum_5000_5999",
                                "6000_6999": "$sum_6000_6999",
                            },
                        }
                    },
                ],  # end event_counts facet
                "time_based_counts": [
                    {
                        "$match": {
                            "created_at": {
                                "$gte": max_time_1month
                            }  # Changed from max_time_1week to include 1 month
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "last_month": {
                                "$sum": 1
                            },  # Count all events within the last month
                            "last_week": {
                                "$sum": {
                                    "$cond": [
                                        {"$gte": ["$created_at", max_time_1week]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "last_24hrs": {
                                "$sum": {
                                    "$cond": [
                                        {"$gte": ["$created_at", max_time_24hr]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                ],  # end time_based_counts facet
                "unique_users": [
                    {"$match": {"kind": {"$gte": 5000, "$lt": 6000}}},
                    {
                        "$group": {
                            "_id": "$kind",
                            "unique_users": {"$addToSet": "$pubkey"},
                        }
                    },
                    {
                        "$project": {
                            "kind": "$_id",
                            "unique_user_count": {"$size": "$unique_users"},
                            "unique_users": 1,
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "per_kind_stats": {
                                "$push": {
                                    "kind": "$kind",
                                    "unique_user_count": "$unique_user_count",
                                }
                            },
                            "all_users": {"$push": "$unique_users"},
                        }
                    },
                    {
                        "$project": {
                            "per_kind_stats": 1,
                            "total_unique_users": {
                                "$size": {
                                    "$reduce": {
                                        "input": "$all_users",
                                        "initialValue": [],
                                        "in": {"$setUnion": ["$$value", "$$this"]},
                                    }
                                }
                            },
                        }
                    },
                ],
                # "payment_stats": [
                #     {
                #         "$match": {
                #             "kind": EventKind.DVM_FEEDBACK.value,
                #             "tags": {
                #                 "$elemMatch": {
                #                     "$and": [
                #                         {
                #                             "$eq": [
                #                                 {"$arrayElemAt": ["$$this", 0]},
                #                                 "status",
                #                             ]
                #                         },
                #                         {
                #                             "$eq": [
                #                                 {"$arrayElemAt": ["$$this", 1]},
                #                                 "payment-required",
                #                             ]
                #                         },
                #                     ]
                #                 }
                #             },
                #         }
                #     },
                #     {"$unwind": "$tags"},
                #     {"$match": {"tags.0": "amount"}},
                #     {
                #         "$group": {
                #             "_id": None,
                #             "total_payments": {"$sum": 1},
                #             "total_amount": {
                #                 "$sum": {"$toInt": {"$arrayElemAt": ["$tags", 1]}}
                #             },
                #         }
                #     },
                # ],
            }
        },
    ]

    results = DB.events.aggregate(pipeline)

    # Since $facet returns a single document, we take the first (and only) result
    facet_results = next(results, None)

    if facet_results is not None:
        for facet_name, facet_data in facet_results.items():
            print(f"Facet: {facet_name}")
            print(json.dumps(facet_data, indent=2))
            print("---")

        # To access specific facets:
        event_counts = facet_results.get("event_counts", [])
        time_based_counts = facet_results.get("time_based_counts", [])

        # Process event_counts
        for count_data in event_counts[0]["details"]:
            print(f"Kind: {count_data['kind']}, Count: {count_data['count']}")

        # Process time_based_counts
        if time_based_counts:
            print(f"Last 24 hours: {time_based_counts[0].get('last_24hrs', 0)}")
            stats["dvm_requests_24_hrs"] = time_based_counts[0].get("last_24hrs")
            print(f"Last week: {time_based_counts[0].get('last_week', 0)}")
            stats["dvm_requests_1_week"] = time_based_counts[0].get("last_week")
            print(f"Last month: {time_based_counts[0].get('last_month', 0)}")
            stats["dvm_requests_1_month"] = time_based_counts[0].get("last_month")

        unique_users_data = facet_results.get("unique_users", [])
        if unique_users_data:
            per_kind_stats = unique_users_data[0].get("per_kind_stats", [])
            total_unique_users = unique_users_data[0].get("total_unique_users", 0)

            print("Unique users per kind:")
            for stat in per_kind_stats:
                print(f"Kind {stat['kind']}: {stat['unique_user_count']} unique users")

            print(f"\nTotal unique users across all kinds: {total_unique_users}")

    else:
        print("No results found")


if __name__ == "__main__":
    """Usage: python compute_stats.py"""

    # compare compute_stats with the mongo db query version

    fast_stats_start_time = datetime.now()
    fast_stats = global_stats_via_big_mongo_query()
    print(f"fast_stats took {datetime.now() - fast_stats_start_time}")
    sys.exit()
    slow_stats_start_time = datetime.now()
    compute_all_stats()
    slow_stats = GlobalStats.compute_stats()
    print(f"slow_stats took {datetime.now()}")

    for k, v in slow_stats.items():
        if k not in fast_stats.keys():
            print(f"slow[{k}] = {v} | <missing in fast_stats>")
        else:
            print(f"slow[{k}] = {v} | fast[{k}] = {fast_stats[k]}")

    try:
        LOGGER.info(f"Starting compute stats process")
        start_time = datetime.now()
        save_global_stats_to_mongodb()
        save_dvm_stats_to_mongodb()
        save_kind_stats_to_mongodb()
        LOGGER.info(
            f"Stats computed and saved to MongoDB. Took {datetime.now() - start_time} seconds."
        )
        LOGGER.info("Goodbye!")
    except Exception as e:
        import traceback

        LOGGER.error(f"Exception occurred: {e}")
        LOGGER.error(traceback.format_exc())
        LOGGER.info("Goodbye!")
