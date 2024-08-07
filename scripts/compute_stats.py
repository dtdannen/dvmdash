import sys
from datetime import datetime, timedelta

from neo4j import (
    GraphDatabase,
)
import nostr_sdk

from pymongo import MongoClient, InsertOne
import json
import os
import time
from pathlib import Path
import loguru
import dotenv
from general.dvm import EventKind
from nostr_sdk import Timestamp, LogLevel


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
    dvm_requests = 0  # k
    dvm_results = 0  # k
    dvm_requests_24_hrs = 0  # k
    dvm_results_24_hrs = 0  # k
    dvm_requests_1_week = 0  # k
    dvm_results_1_week = 0  # k
    dvm_requests_1_month = 0  # k
    dvm_results_1_month = 0  # k
    unique_users = 0  # k
    most_popular_kind = -2  # k
    most_popular_dvm = None  # k

    num_request_kinds = -1
    num_result_kinds = -1
    total_amount_paid_to_dvm_millisats = -1

    num_nip89_profiles = -1

    @classmethod
    def compute_stats(cls):
        stats = {
            "dvm_requests_all_time": GlobalStats.dvm_requests,
            "dvm_results_all_time": GlobalStats.dvm_results,
            "dvm_requests_24_hrs": GlobalStats.dvm_requests_24_hrs,
            "dvm_results_24_hrs": GlobalStats.dvm_results_24_hrs,
            "dvm_requests_1_week": GlobalStats.dvm_requests_1_week,
            "dvm_results_1_week": GlobalStats.dvm_results_1_week,
            "num_dvm_request_kinds": GlobalStats.num_request_kinds,
            "num_dvm_result_kinds": GlobalStats.num_result_kinds,
            "dvm_nip_89s": GlobalStats.num_nip89_profiles,
            "dvm_pub_keys": len(DVM.instances),
            "total_amount_paid_to_dvm_sats": int(
                GlobalStats.total_amount_paid_to_dvm_millisats / 1000
            ),
            "most_popular_kind": GlobalStats.most_popular_kind,
            "most_popular_dvm_npub": GlobalStats.most_popular_dvm.npub_hex,
            "unique_dvm_users": GlobalStats.unique_users,
        }

        try:
            stats[
                "most_popular_dvm_name"
            ] = GlobalStats.most_popular_dvm.nip_89_profile["name"]
        except:
            stats[
                "most_popular_dvm_name"
            ] = f"{GlobalStats.most_popular_dvm.npub_hex[:8]}...{GlobalStats.most_popular_dvm.npub_hex[:-4]}"

        return stats

    @classmethod
    def reset(cls):
        cls.dvm_requests = 0  # k
        cls.dvm_results = 0  # k
        cls.dvm_requests_24_hrs = 0  # k
        cls.dvm_results_24_hrs = 0  # k
        cls.dvm_requests_1_week = 0  # k
        cls.dvm_results_1_week = 0  # k
        cls.dvm_requests_1_month = 0  # k
        cls.dvm_results_1_month = 0  # k
        cls.unique_users = 0  # k
        cls.most_popular_kind = -2  # k
        cls.most_popular_dvm = None  # k

        cls.num_request_kinds = -1
        cls.num_result_kinds = -1
        cls.total_amount_paid_to_dvm_millisats = -1

        cls.num_nip89_profiles = -1


# use this class to track all stats for a given DVM
class DVM:
    instances = {}

    def __init__(self, npub_hex):
        self.npub_hex = npub_hex
        self.jobs_completed_from_mongo = 0  # k
        self.avg_response_time_per_kind_from_neo4j = {}  # k
        self.number_of_jobs_per_kind_from_neo4j = {}  # k
        self.total_millisats_earned_per_kind_from_neo4j = {}  # k
        self.nip_89_profile = None  # k
        self.profile_created_at = None  # k

        DVM.instances[npub_hex] = self

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
            "total_sats_received": int(
                sum(v for v in self.total_millisats_earned_per_kind_from_neo4j.values())
                / 1000
            ),
            "number_jobs_completed": sum(
                v for v in self.number_of_jobs_per_kind_from_neo4j.values()
            ),
        }

        kind_stats = {}
        for kind in set(
            list(self.avg_response_time_per_kind_from_neo4j.keys())
            + list(self.number_of_jobs_per_kind_from_neo4j.keys())
            + list(self.total_millisats_earned_per_kind_from_neo4j.keys())
        ):
            kind_details = {}
            if kind in self.avg_response_time_per_kind_from_neo4j.keys():
                kind_details[
                    "avg_response_time"
                ] = self.avg_response_time_per_kind_from_neo4j[kind]
            if kind in self.total_millisats_earned_per_kind_from_neo4j.keys():
                kind_details["total_sats_earned"] = int(
                    self.total_millisats_earned_per_kind_from_neo4j[kind] / 1000
                )
            if kind in self.number_of_jobs_per_kind_from_neo4j.keys():
                kind_details[
                    "number_of_jobs"
                ] = self.number_of_jobs_per_kind_from_neo4j[kind]
            kind_stats[str(kind)] = kind_details

        stats["kind_stats"] = kind_stats

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

    @classmethod
    def reset(cls):
        cls.instances = {}


class Kind:
    instances = {}

    def __init__(self, kind_number: int):
        self.kind_number = kind_number
        self.unique_users = 0  # k
        self.count_from_mongo = 0  # k
        self.average_response_time_per_dvm = {}
        self.dvm_npubs = []  # k
        self.millisats_earned_per_dvm = {}
        self.job_count_per_dvm = {}
        self.request_count = -1
        self.result_count = -1
        self.data_per_dvm = (
            {}
        )  # key is dvm_npub_hex, value is the sats, response time, and job count for each

        Kind.instances[kind_number] = self

    def add_dvm_npub_earnings_and_response_time(
        self,
        dvm_npub: str,
        millisats_earned: int,
        jobs_performed: int,
        avg_response_time: float,
    ):
        LOGGER.warning(
            f"dvm npub is {dvm_npub} and dvm.npubs is {self.dvm_npubs} and is it inside it? {dvm_npub in self.dvm_npubs}"
        )
        if dvm_npub not in self.dvm_npubs:
            self.dvm_npubs.append(dvm_npub)
            self.millisats_earned_per_dvm[dvm_npub] = millisats_earned
            self.job_count_per_dvm[dvm_npub] = jobs_performed
            self.average_response_time_per_dvm[dvm_npub] = avg_response_time
            self.data_per_dvm[dvm_npub] = {
                "sats_earned": int(millisats_earned / 1000),
                "jobs_performed": jobs_performed,
                "avg_response_time": avg_response_time,
            }
            # if the dvm has a name, then add the name too
            if DVM.get_instance(dvm_npub).nip_89_profile:
                if "display_name" in DVM.get_instance(dvm_npub).nip_89_profile:
                    dvm_name = DVM.get_instance(dvm_npub).nip_89_profile["display_name"]
                    self.data_per_dvm[dvm_npub]["name"] = dvm_name

        else:
            LOGGER.error(
                "DVM npub already exists for this kind, error in db processing"
            )

    def compute_stats(self):
        stats = {
            "total_jobs_requested": self.request_count,
            "total_jobs_performed": self.result_count,
            "number_of_dvms": len(self.dvm_npubs),
            "total_sats_paid_to_dvms": int(
                sum(v for v in self.millisats_earned_per_dvm.values()) / 1000
            ),
            "dvm_npubs": self.dvm_npubs,
            "data_per_dvm": self.data_per_dvm,
        }

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

    @classmethod
    def reset(cls):
        cls.instances = {}


def save_global_stats_to_mongodb():
    collection_name = "new_global_stats"
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
    collection_name = "new_dvm_stats"
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
    collection_name = "new_kind_stats"
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

    current_timestamp = int(Timestamp.now().as_secs())
    max_time_24hr = current_timestamp - (24 * 60 * 60)
    max_time_1week = current_timestamp - (7 * 24 * 60 * 60)
    max_time_1month = current_timestamp - (30 * 24 * 60 * 60)

    pipeline = [
        # we do a big global match, so we can process everything at once
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
                    # create the counts per kind mapping
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
                            "kind_counts": {"$push": "$$ROOT"},
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
                ],  # end event_counts facet
                "time_based_request_counts": [
                    {
                        "$match": {
                            "created_at": {"$gte": max_time_1month},
                            "kind": {"$gte": 5000, "$lte": 5999},
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "last_month_requests": {
                                "$sum": 1
                            },  # Count all events within the last month
                            "last_week_requests": {
                                "$sum": {
                                    "$cond": [
                                        {"$gte": ["$created_at", max_time_1week]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "last_24hrs_requests": {
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
                ],
                "time_based_result_counts": [
                    {
                        "$match": {
                            "created_at": {"$gte": max_time_1month},
                            "kind": {"$gte": 6000, "$lte": 6999},
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "last_month_results": {
                                "$sum": 1
                            },  # Count all events within the last month
                            "last_week_results": {
                                "$sum": {
                                    "$cond": [
                                        {"$gte": ["$created_at", max_time_1week]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "last_24hrs_results": {
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
                ],
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
                "unique_dvms": [
                    # begin the match for finding any event that could be from a DVM so we can get the pubkey
                    {
                        "$match": {
                            "$or": [
                                {"kind": {"$gte": 6000, "$lte": 6999}},
                                {
                                    "$and": [
                                        {"kind": 31990},
                                        {
                                            "$expr": {
                                                "$let": {
                                                    "vars": {
                                                        "kTag": {
                                                            "$filter": {
                                                                "input": "$tags",
                                                                "as": "tag",
                                                                "cond": {
                                                                    "$eq": [
                                                                        {
                                                                            "$arrayElemAt": [
                                                                                "$$tag",
                                                                                0,
                                                                            ]
                                                                        },
                                                                        "k",
                                                                    ]
                                                                },
                                                            }
                                                        }
                                                    },
                                                    "in": {
                                                        "$and": [
                                                            {
                                                                "$gt": [
                                                                    {"$size": "$$kTag"},
                                                                    0,
                                                                ]
                                                            },
                                                            {
                                                                "$let": {
                                                                    "vars": {
                                                                        "kValue": {
                                                                            "$toInt": {
                                                                                "$arrayElemAt": [
                                                                                    {
                                                                                        "$arrayElemAt": [
                                                                                            "$$kTag",
                                                                                            0,
                                                                                        ]
                                                                                    },
                                                                                    1,
                                                                                ]
                                                                            }
                                                                        }
                                                                    },
                                                                    "in": {
                                                                        "$and": [
                                                                            {
                                                                                "$gte": [
                                                                                    "$$kValue",
                                                                                    5000,
                                                                                ]
                                                                            },
                                                                            {
                                                                                "$lte": [
                                                                                    "$$kValue",
                                                                                    5999,
                                                                                ]
                                                                            },
                                                                        ]
                                                                    },
                                                                }
                                                            },
                                                        ]
                                                    },
                                                }
                                            }
                                        },
                                    ]
                                },
                            ]
                        },
                    },
                    # now count the number of 6000-6999 responses from each DVM
                    {
                        "$group": {
                            "_id": "$pubkey",
                            "total_count": {"$sum": 1},
                            "kind_6000_6999_count": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$and": [
                                                {"$gte": ["$kind", 6000]},
                                                {"$lte": ["$kind", 6999]},
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "profile": {
                                "$max": {
                                    "$cond": [
                                        {"$eq": ["$kind", 31990]},
                                        {
                                            "created_at": "$created_at",
                                            "content": "$content",
                                            "tags": "$tags",
                                        },
                                        None,
                                    ]
                                }
                            },
                            "created_at": {"$max": "$created_at"},
                        },
                    },
                    #  Group all DVMs together
                    {
                        "$group": {
                            "_id": None,
                            "unique_dvm_count": {"$sum": 1},
                            "dvm_details": {
                                "$push": {
                                    "pubkey": "$_id",
                                    "total_count": "$total_count",
                                    "kind_6000_6999_count": "$kind_6000_6999_count",
                                    "profile": "$profile",
                                    "created_at": "$created_at",
                                }
                            },
                        }
                    },
                    {"$project": {"unique_dvm_count": 1, "dvm_details": 1}},
                ],
            }
        },
    ]

    results = DB.events.aggregate(pipeline)

    # Since $facet returns a single document, we take the first (and only) result
    facet_results = next(results, None)

    if facet_results is not None:
        # for facet_name, facet_data in facet_results.items():
        #     print(f"Facet: {facet_name}")
        #     print(json.dumps(facet_data, indent=2))
        #     print("---")

        # To access specific facets:
        all_kind_counts = facet_results.get("event_counts", [])[0]["kind_counts"]
        all_request_kinds = set()
        all_result_kinds = set()
        for kind_count in all_kind_counts:
            kind_num = kind_count["kind"]
            kind_count = kind_count["count"]
            Kind.get_instance(kind_num).count_from_mongo = kind_count

            if (
                EventKind.DVM_REQUEST_RANGE_START.value
                <= kind_num
                <= EventKind.DVM_REQUEST_RANGE_END.value
            ):
                all_request_kinds.add(kind_num)
                Kind.get_instance(kind_num).request_count = kind_count
            elif (
                EventKind.DVM_RESULT_RANGE_START.value
                <= kind_num
                <= EventKind.DVM_RESULT_RANGE_END.value
            ):
                all_result_kinds.add(kind_num)
                Kind.get_instance(kind_num).result_count = kind_count

        GlobalStats.num_request_kinds = len(all_request_kinds)
        GlobalStats.num_result_kinds = len(all_result_kinds)

        GlobalStats.dvm_requests = facet_results.get("event_counts", [])[0][
            "sum_5000_5999"
        ]
        GlobalStats.dvm_results = facet_results.get("event_counts", [])[0][
            "sum_6000_6999"
        ]

        time_based_request_counts = facet_results.get("time_based_request_counts", [])[
            0
        ]
        GlobalStats.dvm_requests_24_hrs = time_based_request_counts[
            "last_24hrs_requests"
        ]
        GlobalStats.dvm_requests_1_week = time_based_request_counts[
            "last_week_requests"
        ]
        GlobalStats.dvm_requests_1_month = time_based_request_counts[
            "last_month_requests"
        ]

        time_based_result_counts = facet_results.get("time_based_result_counts", [])[0]
        GlobalStats.dvm_results_24_hrs = time_based_result_counts["last_24hrs_results"]
        GlobalStats.dvm_results_1_week = time_based_result_counts["last_week_results"]
        GlobalStats.dvm_results_1_month = time_based_result_counts["last_month_results"]

        unique_users_data = facet_results.get("unique_users", [])

        if unique_users_data:
            per_kind_stats = unique_users_data[0].get("per_kind_stats", [])
            total_unique_users = unique_users_data[0].get("total_unique_users", 0)
            GlobalStats.unique_users = total_unique_users

            max_kind = None
            max_kind_count = -1
            for stat in per_kind_stats:
                # print(f"Kind {stat['kind']}: {stat['unique_user_count']} unique users")
                Kind.get_instance(stat["kind"]).unique_users = stat["unique_user_count"]
                if stat["unique_user_count"] > max_kind_count:
                    max_kind = stat["kind"]
                    max_kind_count = stat["unique_user_count"]

            GlobalStats.most_popular_kind = max_kind

        unique_dvms = facet_results.get("unique_dvms")[0]["dvm_details"]
        if unique_dvms:
            max_dvm_npub_hex = "<unknown>"
            max_dvm_count = -1
            num_dvm_profiles = 0
            for stat in unique_dvms:
                # print(f"stat is {stat}")
                if stat["profile"] and stat["created_at"]:
                    try:
                        profile_parsed = json.loads(stat["profile"]["content"])
                        DVM.get_instance(stat["pubkey"]).add_nip89_profile(
                            profile_parsed, stat["created_at"]
                        )
                        num_dvm_profiles += 1
                    except Exception as e:
                        LOGGER.warning(
                            f"Could not parse profile for DVM {stat['pubkey']}"
                        )
                        pass

                DVM.get_instance(stat["pubkey"]).jobs_completed_from_mongo = stat[
                    "kind_6000_6999_count"
                ]
                if stat["kind_6000_6999_count"] > max_dvm_count:
                    max_dvm_npub_hex = stat["pubkey"]
                    max_dvm_count = stat["kind_6000_6999_count"]
            GlobalStats.most_popular_dvm = DVM.get_instance(max_dvm_npub_hex)
            GlobalStats.num_nip89_profiles = num_dvm_profiles

    else:
        print("No results found")

    return stats


def dvm_specific_stats_from_neo4j():
    neo4j_query_feedback_events = """
        MATCH (u:User)-[:MADE_EVENT]->(nr:Event:DVMRequest)
        MATCH (d:DVM)-[:MADE_EVENT]->(ns:Event:DVMResult)-[:RESULT_FOR]->(nr)
        MATCH (d:DVM)-[:MADE_EVENT]->(f:FeedbackPaymentRequest)-[:FEEDBACK_FOR]->(nr)
        WITH d, nr, ns, f,
             ns.created_at - nr.created_at AS response_time_secs,
             apoc.convert.fromJsonList(f.tags) AS parsed_tags,
             nr.kind AS request_kind
        WITH d, response_time_secs, request_kind, parsed_tags,
             [tag IN parsed_tags WHERE tag[0] = 'amount'][0][1] AS amount_str
        WHERE amount_str IS NOT NULL
        WITH d, response_time_secs, request_kind, toInteger(amount_str) AS amount
        WHERE amount IS NOT NULL
        WITH 
            d.npub_hex AS dvm_npub_hex,
            request_kind,
            avg(response_time_secs) AS avg_response_time,
            count(*) AS jobs_count,
            sum(amount) AS total_amount
        WITH collect({
            dvm_npub_hex: dvm_npub_hex,
            kind: request_kind,
            avg_response_time: avg_response_time,
            jobs_count: jobs_count,
            total_amount: total_amount
        }) AS dvm_kind_stats
        
        // Calculate DVM totals
        UNWIND dvm_kind_stats AS stat
        WITH dvm_kind_stats, stat.dvm_npub_hex AS dvm, 
             sum(stat.total_amount) AS dvm_total_amount,
             sum(stat.jobs_count) AS dvm_total_jobs,
             avg(stat.avg_response_time) AS dvm_avg_response_time
        WITH dvm_kind_stats, collect({
            dvm: dvm,
            dvm_total_amount: dvm_total_amount,
            dvm_total_jobs: dvm_total_jobs,
            dvm_avg_response_time: dvm_avg_response_time
        }) AS dvm_totals
        
        // Calculate overall totals and combine with original stats
        UNWIND dvm_kind_stats AS stat
        WITH stat, dvm_totals, dvm_kind_stats,
             sum(stat.total_amount) AS overall_total_amount,
             sum(stat.jobs_count) AS overall_total_jobs,
             avg(stat.avg_response_time) AS overall_avg_response_time
        WITH stat, dvm_totals, 
             overall_total_amount, overall_total_jobs, overall_avg_response_time,
             [x IN dvm_totals WHERE x.dvm = stat.dvm_npub_hex][0] AS dvm_total
        
        RETURN 
            stat.dvm_npub_hex AS dvm_npub_hex,
            stat.kind AS kind,
            stat.avg_response_time AS avg_response_time,
            stat.jobs_count AS jobs_count,
            stat.total_amount AS total_amount,
            dvm_total.dvm_total_amount AS dvm_total_amount,
            dvm_total.dvm_total_jobs AS dvm_total_jobs,
            dvm_total.dvm_avg_response_time AS dvm_avg_response_time,
            overall_total_amount,
            overall_total_jobs,
            overall_avg_response_time
        ORDER BY dvm_npub_hex, stat.jobs_count DESC
    """

    with NEO4J_DRIVER.session() as session:
        try:
            result = session.execute_read(
                lambda tx: list(tx.run(neo4j_query_feedback_events))
            )
            total_amount_paid_to_all_dvms = 0
            for record in result:
                dvm_npub_hex = record["dvm_npub_hex"]
                kind_number = record["kind"]
                average_response_time_secs_per_kind = record["avg_response_time"]
                jobs_performed_per_kind = record["jobs_count"]
                amount_paid_for_this_kind = record["total_amount"]

                dvm_instance = DVM.get_instance(dvm_npub_hex)
                dvm_instance.avg_response_time_per_kind_from_neo4j[
                    kind_number
                ] = average_response_time_secs_per_kind
                dvm_instance.number_of_jobs_per_kind_from_neo4j[
                    kind_number
                ] = jobs_performed_per_kind
                dvm_instance.total_millisats_earned_per_kind_from_neo4j[
                    kind_number
                ] = amount_paid_for_this_kind

                Kind.get_instance(kind_number).add_dvm_npub_earnings_and_response_time(
                    dvm_npub_hex,
                    amount_paid_for_this_kind,
                    jobs_performed_per_kind,
                    average_response_time_secs_per_kind,
                )

                total_amount_paid_to_all_dvms += amount_paid_for_this_kind

            GlobalStats.total_amount_paid_to_dvm_millisats = (
                total_amount_paid_to_all_dvms
            )

        except Exception as e:
            import traceback

            LOGGER.error(f"Failed to execute Neo4j query: {e}")
            LOGGER.error(traceback.format_exc())


def compute_basic_stats_from_db_queries():
    """Step 1"""
    # mongo query
    global_stats_via_big_mongo_query()
    # neo4j query
    dvm_specific_stats_from_neo4j()


def save_new_stats():
    """Step 2"""
    save_global_stats_to_mongodb()
    save_dvm_stats_to_mongodb()
    save_kind_stats_to_mongodb()


import signal


def signal_handler(sig, frame):
    print("You pressed Ctrl+C!")
    sys.exit(0)


if __name__ == "__main__":
    """Usage: python compute_stats.py"""

    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            GlobalStats.reset()
            DVM.reset()
            Kind.reset()

            start_time = datetime.now()
            compute_basic_stats_from_db_queries()
            save_new_stats()

            LOGGER.info(
                f"there are {len(DVM.instances)} DVM Instances and {len(Kind.instances)} Kind Instances"
            )

            LOGGER.info(
                f"Stats computed and saved to MongoDB. Took {datetime.now() - start_time} seconds."
            )
            LOGGER.info("Iteration complete. Press Ctrl+C to exit.")

        except Exception as e:
            import traceback

            LOGGER.error(f"Exception occurred: {e}")
            LOGGER.error(traceback.format_exc())

        # Optional: add a delay between iterations
        # import time
        time.sleep(0.5)  # Wait for 60 seconds before the next iteration
