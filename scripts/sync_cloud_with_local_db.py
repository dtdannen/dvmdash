import os
from pathlib import Path
from pymongo import MongoClient
from mongita import MongitaClientDisk
import dotenv

# Load environment variables from .env file
env_path = Path(".env")
if env_path.is_file():
    print(f"Loading environment from {env_path.resolve()}")
    dotenv.load_dotenv(env_path, verbose=True, override=True)
else:
    print(f".env file not found at {env_path}")
    raise FileNotFoundError(f".env file not found at {env_path}")

# Connect to the cloud MongoDB
mongo_client = MongoClient(os.getenv("MONGO_URI"), tls=True)
cloud_db = mongo_client["dvmdash"]

# Connect to the local Mongita database
mongita_client = MongitaClientDisk()
local_db = mongita_client.dvmdash

# Retrieve all events from the local Mongita database
print("Retrieving all events from the local Mongita database...")
local_events = list(local_db["events"].find())
print(f"Events retrieved from the local Mongita database, now syncing to the cloud")

# Sync the events to the cloud MongoDB
if local_events:
    # Get the _ids of all events in the cloud database
    cloud_event_ids = set(
        event["_id"] for event in cloud_db["events"].find({}, {"_id": 1})
    )

    # Filter out the events that already exist in the cloud database
    new_events = [
        event for event in local_events if event["_id"] not in cloud_event_ids
    ]

    if new_events:
        try:
            result = cloud_db["events"].insert_many(new_events, ordered=False)
            print(
                f"Finished syncing {len(result.inserted_ids)} new events to the cloud MongoDB."
            )
        except Exception as e:
            print(f"Error inserting events into the cloud MongoDB: {e}")
    else:
        print("No new events found in the local Mongita database.")
else:
    print("No events found in the local Mongita database.")
