# This script grabs all the events from the online db and saves them to the local mongita db
# in order to make local development have access to recent events

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

# Retrieve all events from the cloud database
print("Retrieving all events from the cloud database...this may take a while...")
events = list(cloud_db["events"].find())
print(f"Events retrieved from the cloud database, now saving to local Mongita")
# Save the events to the local Mongita database
if events:
    try:
        result = local_db["events"].insert_many(events, ordered=False)
        print(
            f"Finished writing {len(result.inserted_ids)} events to the local Mongita database."
        )
    except Exception as e:
        print(f"Error inserting events into the local Mongita database: {e}")
else:
    print("No events found in the cloud database.")

# print how many events are in the mongita db
print(
    f"There are {local_db['events'].count_documents({})} documents in events collection"
)
