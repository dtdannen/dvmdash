#!/usr/bin/env python3
import os
import sys
import psycopg2
import time
import random
import argparse
import logging
from collections import Counter
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("count_unique_dvm_authors")

# Load environment variables
load_dotenv()

# Database connection parameters
DB_HOST = os.getenv("PROD_POSTGRES_HOST")
DB_PORT = os.getenv("PROD_POSTGRES_PORT")
DB_NAME = os.getenv("PROD_POSTGRES_DB")
DB_USER = os.getenv("PROD_POSTGRES_USER")
DB_PASSWORD = os.getenv("PROD_POSTGRES_PASS")


def connect_to_database():
    """
    Connect to the PostgreSQL database.

    Returns:
        connection: PostgreSQL database connection
    """
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        logger.info(f"Connected to database {DB_NAME} on {DB_HOST}")
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        sys.exit(1)


def get_31990_event_count(cursor):
    """
    Get the count of kind 31990 events.

    Args:
        cursor: Database cursor

    Returns:
        int: Number of kind 31990 events
    """
    cursor.execute("SELECT COUNT(*) FROM raw_events WHERE kind = 31990")
    return cursor.fetchone()[0]


def count_unique_authors(cursor, batch_size=1000, limit=None, show_top_n=10):
    """
    Count unique authors of kind 31990 events.

    Args:
        cursor: Database cursor
        batch_size: Number of events to process in each batch
        limit: Maximum number of events to process (for testing)
        show_top_n: Number of top authors to display

    Returns:
        tuple: (total_events, unique_authors, author_counts)
    """
    total_count = get_31990_event_count(cursor)
    
    # Apply limit if specified
    if limit and limit < total_count:
        total_count = limit
        logger.info(f"Limited to processing {limit:,} kind 31990 events")

    logger.info(f"Processing {total_count:,} kind 31990 events")

    if total_count == 0:
        return 0, 0, {}

    # Set to track unique authors
    unique_authors = set()
    # Counter to track number of events per author
    author_counts = Counter()
    
    processed = 0
    start_time = time.time()

    # Process in batches
    offset = 0
    while processed < total_count:
        # Adjust batch size for the last batch
        current_batch_size = min(batch_size, total_count - processed)

        # Add a random sleep to prevent hammering the database
        sleep_time = random.uniform(0.1, 0.5)
        time.sleep(sleep_time)

        # Query for a batch of events
        cursor.execute(
            """
            SELECT pubkey
            FROM raw_events
            WHERE kind = 31990
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (current_batch_size, offset),
        )

        batch = cursor.fetchall()
        if not batch:
            break

        # Process each event in the batch
        for row in batch:
            pubkey = row[0]  # Get the author pubkey
            unique_authors.add(pubkey)
            author_counts[pubkey] += 1

        processed += len(batch)
        offset += current_batch_size

        # Calculate and display progress
        elapsed_time = time.time() - start_time
        events_per_second = processed / elapsed_time if elapsed_time > 0 else 0
        estimated_remaining = (
            (total_count - processed) / events_per_second
            if events_per_second > 0
            else 0
        )

        logger.info(
            f"Processed {processed:,}/{total_count:,} kind 31990 events "
            f"({(processed/total_count)*100:.2f}%) - "
            f"Speed: {events_per_second:.2f} events/sec - "
            f"Est. remaining: {estimated_remaining/60:.2f} minutes"
        )

    return total_count, len(unique_authors), author_counts


def main():
    """Main function to count unique authors of kind 31990 events."""
    parser = argparse.ArgumentParser(
        description="Count unique authors of kind 31990 events (NIP-89 announcements)."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for processing (default: 1000)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of events to process (for testing)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top authors to display (default: 10)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    start_time = time.time()
    logger.info("Starting count of unique authors of kind 31990 events")

    # Connect to the database
    conn = connect_to_database()
    cursor = conn.cursor()

    try:
        # Count unique authors
        total_events, unique_authors, author_counts = count_unique_authors(
            cursor, args.batch_size, args.limit, args.top
        )

        # Print results
        print("\n===== RESULTS =====")
        print(f"Total kind 31990 events: {total_events:,}")
        print(f"Number of unique DVM authors: {unique_authors:,}")
        
        # Display top authors
        if author_counts:
            print(f"\nTop {args.top} authors by number of announcements:")
            for i, (pubkey, count) in enumerate(author_counts.most_common(args.top), 1):
                print(f"{i}. {pubkey[:8]}...{pubkey[-8:]} - {count:,} announcements")

        # Log summary
        elapsed_time = time.time() - start_time
        logger.info(f"Analysis completed in {elapsed_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
