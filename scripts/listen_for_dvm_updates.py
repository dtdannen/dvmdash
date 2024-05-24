"""
This script listens for updates to mongodb and triggers a function to update the dvm summary pages.
"""

from pymongo import MongoClient
from bson.codec_options import CodecOptions
from datetime import datetime, timedelta
import statistics
import loguru
import os
import sys


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

LOGGER = setup_logging()
LOGGER.info("Starting up in current directory: ", os.getcwd())


def setup_database():
    LOGGER.debug("os.getenv('USE_MONGITA', False): ", os.getenv("USE_MONGITA", False))

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


def compute_summary(events_collection, summary_collection):
    pass  # get all events related to this dvm

    for change in change_stream:
        event = change["fullDocument"]
        dvm_id = event["dvm_id"]
        kind = event["kind"]
        created_at = event["created_at"]
        amount = event.get("amount", 0)
        feedback = event.get("feedback", None)
        response_time = event.get("response_time", None)

        summary = summary_collection.find_one({"dvm_id": dvm_id})

        if not summary:
            summary = {
                "dvm_id": dvm_id,
                "latest_nip89_profile": None,
                "first_seen": created_at,
                "call_count_total": 0,
                "call_count_weekly": 0,
                "call_count_monthly": 0,
                "response_count_total": 0,
                "response_count_weekly": 0,
                "response_count_monthly": 0,
                "total_money_paid": 0,
                "money_paid_weekly": 0,
                "money_paid_monthly": 0,
                "feedback_positive_total": 0,
                "feedback_negative_total": 0,
                "feedback_positive_weekly": 0,
                "feedback_negative_weekly": 0,
                "feedback_positive_monthly": 0,
                "feedback_negative_monthly": 0,
                "response_time_median": 0,
                "response_time_mean": 0,
                "response_time_last_5": [],
            }

        # Update based on event kind
        if kind == 31990:  # NIP-89 profile update
            summary["latest_nip89_profile"] = event

        summary["call_count_total"] += 1
        summary["total_money_paid"] += amount

        if feedback == "positive":
            summary["feedback_positive_total"] += 1
        elif feedback == "negative":
            summary["feedback_negative_total"] += 1

        if response_time:
            summary["response_time_last_5"].append(response_time)
            if len(summary["response_time_last_5"]) > 5:
                summary["response_time_last_5"].pop(0)
            summary["response_time_median"] = statistics.median(
                summary["response_time_last_5"]
            )
            summary["response_time_mean"] = statistics.mean(
                summary["response_time_last_5"]
            )

        # Update weekly and monthly counts based on the current time
        now = datetime.utcnow()
        week_ago = now - timedelta(weeks=1)
        month_ago = now - timedelta(days=30)

        summary["call_count_weekly"] = events_collection.count_documents(
            {"dvm_id": dvm_id, "created_at": {"$gte": week_ago}}
        )
        summary["call_count_monthly"] = events_collection.count_documents(
            {"dvm_id": dvm_id, "created_at": {"$gte": month_ago}}
        )
        summary["response_count_weekly"] = events_collection.count_documents(
            {
                "dvm_id": dvm_id,
                "created_at": {"$gte": week_ago},
                "kind": {"$gte": 5000, "$lte": 6999},
            }
        )
        summary["response_count_monthly"] = events_collection.count_documents(
            {
                "dvm_id": dvm_id,
                "created_at": {"$gte": month_ago},
                "kind": {"$gte": 5000, "$lte": 6999},
            }
        )
        summary["money_paid_weekly"] = sum(
            event["amount"]
            for event in events_collection.find(
                {"dvm_id": dvm_id, "created_at": {"$gte": week_ago}}
            )
        )
        summary["money_paid_monthly"] = sum(
            event["amount"]
            for event in events_collection.find(
                {"dvm_id": dvm_id, "created_at": {"$gte": month_ago}}
            )
        )
        summary["feedback_positive_weekly"] = events_collection.count_documents(
            {"dvm_id": dvm_id, "created_at": {"$gte": week_ago}, "feedback": "positive"}
        )
        summary["feedback_negative_weekly"] = events_collection.count_documents(
            {"dvm_id": dvm_id, "created_at": {"$gte": week_ago}, "feedback": "negative"}
        )
        summary["feedback_positive_monthly"] = events_collection.count_documents(
            {
                "dvm_id": dvm_id,
                "created_at": {"$gte": month_ago},
                "feedback": "positive",
            }
        )
        summary["feedback_negative_monthly"] = events_collection.count_documents(
            {
                "dvm_id": dvm_id,
                "created_at": {"$gte": month_ago},
                "feedback": "negative",
            }
        )

        # Update the summary document
        summary_collection.update_one(
            {"dvm_id": dvm_id}, {"$set": summary}, upsert=True
        )


if __name__ == "__main__":
    db = setup_database()
    events_collection = db["events"]
    summary_collection = db["dvm_summary"]

    pipeline = [{"$match": {"operationType": {"$in": ["insert", "update"]}}}]
    change_stream = events_collection.watch(pipeline)

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
