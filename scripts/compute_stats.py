import sys
from datetime import datetime, timedelta
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
    mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True)
    db = mongo_client["dvmdash"]

    try:
        result = db["events"].count_documents({})
        LOGGER.info(f"There are {result} documents in events collection")
    except Exception as e:
        LOGGER.error("Could not count documents in db")
        import traceback

        traceback.print_exc()

    LOGGER.info("Connected to cloud mongo db")

    return db


DB = setup_database()


def compute_stats():
    stats = {}

    # get the number of events in the database
    num_dvm_events_in_db = DB["events"].count_documents({})
    stats["num_dvm_events_in_db"] = num_dvm_events_in_db

    # get the number of unique kinds of all events
    all_dvm_events_cursor = DB["events"].find(
        {"kind": {"$gte": 5000, "$lte": 6999, "$nin": EventKind.get_bad_dvm_kinds()}}
    )
    all_dvm_events = list(all_dvm_events_cursor)

    # print the memory usages of all events so far:
    memory_usage = sys.getsizeof(all_dvm_events)
    # Convert memory usage to megabytes
    memory_usage_mb = memory_usage / (1024 * 1024)
    LOGGER.info(f"Memory usage of all_dvm_events: {memory_usage_mb:.2f} MB")

    dvm_nip89_profiles = {}

    for nip89_event in DB["events"].find({"kind": 31990}):
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

    request_kinds_counts = {}
    response_kinds_counts = {}
    zap_counts = 0
    dm_counts = 0
    uncategorized_counts = 0
    num_dvm_request_events = 0
    num_dvm_response_events = 0

    current_timestamp = Timestamp.now()
    current_secs = current_timestamp.as_secs()

    max_time_24hr = Timestamp.from_secs(current_secs - (24 * 60 * 60))
    max_time_1week = Timestamp.from_secs(current_secs - (7 * 24 * 60 * 60))

    # TODO - alter this to make sure bad dvm kinds are ignored
    dvm_tasks_24h = DB["events"].count_documents(
        {
            "created_at": {"$gte": max_time_24hr.as_secs()},
            "kind": {"$gte": 5000, "$lte": 5999},
        }
    )
    stats["num_dvm_tasks_24h"] = dvm_tasks_24h

    # TODO - alter this to make sure bad dvm kinds are ignored
    dvm_results_24h = DB["events"].count_documents(
        {
            "created_at": {"$gte": max_time_24hr.as_secs()},
            "kind": {"$gte": 6000, "$lte": 6999},
        }
    )
    stats["num_dvm_results_24h"] = dvm_results_24h

    # TODO - alter this to make sure bad dvm kinds are ignored
    dvm_tasks_1week = DB["events"].count_documents(
        {
            "created_at": {"$gte": max_time_1week.as_secs()},
            "kind": {"$gte": 5000, "$lte": 5999},
        }
    )
    stats["num_dvm_tasks_1week"] = dvm_tasks_1week

    # TODO - alter this to make sure bad dvm kinds are ignored
    # TODO - by computing in the loop
    dvm_results_1week = DB["events"].events.count_documents(
        {
            "created_at": {"$gte": max_time_1week.as_secs()},
            "kind": {"$gte": 6000, "$lte": 6999},
        }
    )

    stats["num_dvm_results_1week"] = dvm_results_1week

    # pub ids of all dvms
    dvm_job_results = {}

    # pub ids of all dvm requests - these are probably people?
    dvm_job_requests = {}

    for dvm_event_i in all_dvm_events:
        if "kind" in dvm_event_i:
            kind_num = dvm_event_i["kind"]

            if (
                5000 <= kind_num <= 5999
                and kind_num not in EventKind.get_bad_dvm_kinds()
            ):
                num_dvm_request_events += 1
                if kind_num in request_kinds_counts:
                    request_kinds_counts[kind_num] += 1
                else:
                    request_kinds_counts[kind_num] = 1

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
                if kind_num in response_kinds_counts:
                    response_kinds_counts[kind_num] += 1
                else:
                    response_kinds_counts[kind_num] = 1

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
    for pub_key, count in dvm_job_results.items():
        if pub_key in dvm_nip89_profiles and "name" in dvm_nip89_profiles[pub_key]:
            dvm_job_results_names[dvm_nip89_profiles[pub_key]["name"]] = count
            labels_to_pubkeys[dvm_nip89_profiles[pub_key]["name"]] = pub_key
        else:
            dvm_job_results_names[pub_key[:6]] = count
            labels_to_pubkeys[pub_key[:6]] = pub_key

    stats["num_dvm_kinds"] = len(list(request_kinds_counts.keys()))
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

    return stats


def save_stats_to_mongodb(stats):
    collection = DB["stats"]

    current_time = datetime.now()
    stats_document = {"timestamp": current_time, **stats}

    LOGGER.info(f"About to saving stats to MongoDB: {stats}")

    collection.insert_one(stats_document)

    LOGGER.info(f"Stats saved to MongoDB: {stats_document}")


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
