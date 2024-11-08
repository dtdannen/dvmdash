from general.metrics import GlobalStats, DVMStats, KindStats
import json
from pymongo import MongoClient
from typing import List, Dict, Any


def load_test_events_from_file():
    """
    We have many DVM events exported from a DB and saved into a file, that we will use for timing tests
    """

    filepath = "data/dvmdash.events.json"

    with open(filepath, "r") as file:
        return json.load(file)


if __name__ == "__main__":
    # Load test events from file
    test_events = load_test_events_from_file()

    # Create a MongoClient instance
    client = MongoClient("mongodb://localhost:27017/")

    # Get the database
    db = client["nostr"]

    # Get the collection
    events = db["events"]

    # Insert the test events into the database
    events.insert_many(test_events)

    # Create a GlobalStats instance
    global_stats = GlobalStats(db)

    # Compute the global stats
    global_stats.compute()

    # Get the global stats
    stats = global_stats.get_summary_data()

    # Print the stats
    print(stats)
