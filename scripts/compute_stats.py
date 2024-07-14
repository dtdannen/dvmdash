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
from tqdm import tqdm
import re


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

    return db


DB = setup_database()


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
    stats = {}

    # get the number of events in the database
    num_dvm_events_in_db = DB.events.count_documents({})
    stats["num_dvm_events_in_db"] = num_dvm_events_in_db

    # get the number of unique kinds of all events
    all_dvm_events_cursor = DB.events.find(
        {"kind": {"$gte": 5000, "$lte": 6999, "$nin": EventKind.get_bad_dvm_kinds()}}
    )
    all_dvm_events = list(all_dvm_events_cursor)

    # print the memory usages of all events so far:
    memory_usage = sys.getsizeof(all_dvm_events)
    # Convert memory usage to megabytes
    memory_usage_mb = memory_usage / (1024 * 1024)
    print(f"Memory usage of all_dvm_events: {memory_usage_mb:.2f} MB")

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

    query = {
        "kind": 7000,
        "tags": {
            "$all": [["status", "payment-required"]],
        },
    }

    payment_requests = list(DB.events.find(query))

    total_number_of_payments_requests = len(payment_requests)
    total_amount_millisats = 0
    average_amount_millisats = 0

    for payment_request in payment_requests:
        try:
            tags = payment_request["tags"]
            for tag in tags:
                if tag[0] == "amount":
                    total_amount_millisats += int(tag[1])
                    break
        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {payment_request['id']}: {str(e)}")
            # Skip processing tags for this record and continue with the next one

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

    # get all zap receipts to calculate how much money has actually been paid to DVMs

    zap_receipts = list(DB.events.find({"kind": 9735}))

    total_amount_paid_millisats = 0
    total_number_of_payment_receipts = 0
    bolt11_invoice_amount_regex_pattern = r"lnbc(\d+)"
    for zap_receipt in zap_receipts:
        try:
            tags = zap_receipt["tags"]
            has_bolt11_invoice = False
            amount_millisats = -1
            amount_from_bolt_invoice = -1
            has_preimage = False
            for tag in tags:
                # check that the tag has a bolt11 invoice
                # print(f"tag is {tag}")
                if tag[0] == "bolt11":
                    has_bolt11_invoice = True

                    invoice_str = tag[1]

                    # get the amount from the bolt 11 invoice:
                    match = re.search(bolt11_invoice_amount_regex_pattern, invoice_str)
                    if match:
                        amount_from_bolt_invoice = int(match.group(1))
                        print(f"Amount from bolt invoice: {amount_from_bolt_invoice}")
                elif tag[0] == "description":
                    # this should point to a new event that is the zap request
                    zap_request = json.loads(tag[1])
                    if "kind" in zap_request and zap_request["kind"] == 9734:
                        # this is a zap request
                        # check if the zap request has a bolt11 invoice
                        zap_request_tags = zap_request["tags"]
                        for zap_request_tag in zap_request_tags:
                            if zap_request_tag[0] == "amount":
                                amount_millisats = int(zap_request_tag[1])
                                break
                elif tag[0] == "preimage":
                    has_preimage = True

            if not has_bolt11_invoice:
                print(f"Zap receipt {zap_receipt['id']} does not have a bolt11 invoice")
                continue

            if not has_preimage:
                print(f"Zap receipt {zap_receipt['id']} does not have a preimage")
                continue

            if amount_millisats < 0 and amount_from_bolt_invoice < 0:
                print(
                    f"Zap receipt {zap_receipt['id']} is missing amount or does not have a valid amount"
                )
                continue

            # if we get here, we have a valid zap receipt
            print(f"Zap receipt {zap_receipt['id']} has a valid bolt11 invoice")
            if amount_from_bolt_invoice > 0:
                total_amount_paid_millisats += amount_from_bolt_invoice * 100
            else:
                total_amount_paid_millisats += amount_millisats
            total_number_of_payment_receipts += 1

        except (ValueError, SyntaxError) as e:
            print(f"Error parsing tags for record {zap_receipt['id']}: {str(e)}")
            # Skip processing tags for this record and continue with the next one
        except Exception as e:
            print(f"Error processing zap receipt {zap_receipt['id']}: {str(e)}")
            import traceback

            print(f"Traceback: {traceback.format_exc()}")

    stats["total_amount_dvm_paid_sats"] = int(total_amount_paid_millisats / 1000)
    stats["total_number_of_payment_receipts"] = total_number_of_payment_receipts
    stats["total_average_amount_dvm_paid_sats"] = int(
        total_amount_paid_millisats / 1000 / total_number_of_payment_receipts
    )

    return stats


def save_stats_to_mongodb(stats):
    collection_name = "stats"
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