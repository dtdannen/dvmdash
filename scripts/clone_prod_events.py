from pymongo import MongoClient
from tqdm import tqdm
import time


def clone_collection_with_indexes(
    source_uri, dest_uri, db_name, source_collection, dest_collection
):
    """
    Clone a MongoDB collection including all its indexes to a new collection.
    Can be in the same or different database/cluster.

    Parameters:
    source_uri: Connection string for source MongoDB
    dest_uri: Connection string for destination MongoDB
    db_name: Database name
    source_collection: Source collection name
    dest_collection: Destination collection name
    """
    # Connect to source and destination
    source_client = MongoClient(source_uri)
    dest_client = MongoClient(dest_uri)

    # Get database and collection objects
    source_db = source_client[db_name]
    dest_db = dest_client[db_name]
    source_coll = source_db[source_collection]
    dest_coll = dest_db[dest_collection]

    # Get all indexes from source collection
    indexes = source_coll.list_indexes()
    index_info = []

    # Store index information
    for index in indexes:
        if index["name"] != "_id_":  # Skip default _id index
            index_info.append(
                {
                    "keys": index["key"],
                    "name": index["name"],
                    "unique": index.get("unique", False),
                    "sparse": index.get("sparse", False),
                    "background": True,
                    "weights": index.get("weights", None),
                    "default_language": index.get("default_language", None),
                    "language_override": index.get("language_override", None),
                    "expireAfterSeconds": index.get("expireAfterSeconds", None),
                }
            )

    # Copy data in batches
    batch_size = 1000
    total_docs = source_coll.count_documents({})

    print(f"Copying {total_docs} documents...")

    for i in tqdm(range(0, total_docs, batch_size)):
        batch = list(source_coll.find().skip(i).limit(batch_size))
        if batch:
            dest_coll.insert_many(batch)

    # Recreate indexes
    print("Creating indexes...")
    for index in index_info:
        # Remove None values from index options
        index_options = {
            k: v for k, v in index.items() if k not in ["keys"] and v is not None
        }

        print(f"Creating index: {index['name']}")
        dest_coll.create_index(list(index["keys"].items()), **index_options)

    print("Clone complete!")

    # Return some statistics
    return {
        "documents_copied": dest_coll.count_documents({}),
        "indexes_created": len(index_info),
        "index_names": [idx["name"] for idx in index_info],
    }


# Example usage:
if __name__ == "__main__":
    # Example connection strings
    source_uri = "mongodb://source-server:27017/"
    dest_uri = "mongodb://destination-server:27017/"

    stats = clone_collection_with_indexes(
        source_uri=source_uri,
        dest_uri=dest_uri,
        db_name="your_database",
        source_collection="source_collection",
        dest_collection="destination_collection",
    )

    print("\nCloning Statistics:")
    print(f"Documents Copied: {stats['documents_copied']}")
    print(f"Indexes Created: {stats['indexes_created']}")
    print("Index Names:", ", ".join(stats["index_names"]))
