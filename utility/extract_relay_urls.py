#!/usr/bin/env python3
import os
import psycopg2
import json
import ast
from collections import Counter
from dotenv import load_dotenv
import time
import argparse
import gc
import psutil
import sys

# Load environment variables from .env file
load_dotenv()

# Database connection parameters
DB_HOST = os.getenv("PROD_POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("PROD_POSTGRES_PORT", "5432")
DB_NAME = os.getenv("PROD_POSTGRES_DB", "dvmdash_pipeline")
DB_USER = os.getenv("PROD_POSTGRES_USER", "devuser")
DB_PASSWORD = os.getenv("PROD_POSTGRES_PASS", "devpass")


def get_memory_usage():
    """Get the current memory usage of the process in MB."""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    # Convert from bytes to MB
    return memory_info.rss / (1024 * 1024)


def extract_relay_urls(tags_data):
    """
    Extract relay URLs from the tags data.

    Args:
        tags_data: Tags data from the database (already parsed as a Python list)

    Returns:
        list: List of relay URLs found
    """
    relay_urls = []

    if not tags_data:
        return relay_urls

    # The tags_data is already a Python list (array of arrays)
    # Each inner array is a tag, where the first element is the tag name
    for tag_array in tags_data:
        # Check if this is a "relays" tag
        if tag_array and len(tag_array) > 1 and tag_array[0] == "relays":
            # Add all elements after "relays" to our list
            relay_urls.extend(tag_array[1:])

    return relay_urls


def process_in_batches(
    cursor, batch_size=10000, row_limit=None, checkpoint_interval=1000000
):
    """
    Process the database in batches to extract relay URLs.

    Args:
        cursor: Database cursor
        batch_size: Number of rows to process in each batch
        row_limit: Maximum number of rows to process (for testing)
        checkpoint_interval: Number of rows after which to save intermediate results

    Returns:
        set: Set of unique relay URLs
        Counter: Counter of relay URL frequencies
        int: Total number of rows processed
        int: Number of rows containing relay URLs
    """
    unique_relays = set()
    relay_counter = Counter()
    total_rows = 0
    rows_with_relays = 0
    last_checkpoint = 0
    batch_start_time = time.time()

    # Get an estimate of total rows
    cursor.execute("SELECT COUNT(*) FROM raw_events WHERE tags IS NOT NULL")
    estimated_total = cursor.fetchone()[0]

    # Apply row limit if specified
    if row_limit is not None and row_limit < estimated_total:
        estimated_total = row_limit
        print(f"Limited to processing {row_limit:,} rows")
    else:
        print(f"Estimated total rows to process: {estimated_total:,}")

    start_time = time.time()
    offset = 0

    # Create a temporary file to store intermediate results
    temp_relays_file = "temp_relay_urls.txt"
    temp_freq_file = "temp_relay_frequencies.txt"

    # Initial memory usage
    initial_memory = get_memory_usage()
    print(f"Initial memory usage: {initial_memory:.2f} MB")

    while True:
        # Check if we've reached the row limit
        if row_limit is not None and total_rows >= row_limit:
            break

        # Adjust batch size for the last batch if we have a row limit
        current_batch_size = batch_size
        if row_limit is not None and total_rows + batch_size > row_limit:
            current_batch_size = row_limit - total_rows

        # Reset batch timing
        batch_start_time = time.time()

        # Measure database query time
        db_query_start = time.time()
        
        # Use a more efficient query approach without OFFSET
        if offset == 0:
            # First batch
            cursor.execute(
                "SELECT id, tags FROM raw_events WHERE tags IS NOT NULL ORDER BY id LIMIT %s",
                (current_batch_size,),
            )
        else:
            # Subsequent batches - use the last ID as a starting point
            cursor.execute(
                "SELECT id, tags FROM raw_events WHERE tags IS NOT NULL AND id > %s ORDER BY id LIMIT %s",
                (last_id, current_batch_size),
            )
            
        batch = cursor.fetchall()
        db_query_time = time.time() - db_query_start
        db_rows_per_second = len(batch) / db_query_time if db_query_time > 0 else 0
        if not batch:
            break

        # Process this batch
        batch_relays = set()
        batch_counter = Counter()
        
        # Keep track of the last ID we've processed
        last_id = None
        
        for row in batch:
            last_id = row[0]  # Store the ID
            tags_data = row[1]  # Get the tags data
            
            relay_urls = extract_relay_urls(tags_data)
            if relay_urls:
                rows_with_relays += 1
                batch_relays.update(relay_urls)
                batch_counter.update(relay_urls)

        # Update the main counters with this batch's results
        unique_relays.update(batch_relays)
        relay_counter.update(batch_counter)

        total_rows += len(batch)
        offset += batch_size

        # Get current memory usage
        current_memory = get_memory_usage()
        memory_change = current_memory - initial_memory

        # Calculate and display progress
        elapsed_time = time.time() - start_time
        batch_time = time.time() - batch_start_time
        rows_per_second = total_rows / elapsed_time if elapsed_time > 0 else 0
        batch_rows_per_second = len(batch) / batch_time if batch_time > 0 else 0
        estimated_remaining = (
            (estimated_total - total_rows) / rows_per_second
            if rows_per_second > 0
            else 0
        )

        print(
            f"Processed {total_rows:,}/{estimated_total:,} rows ({(total_rows/estimated_total)*100:.2f}%) - "
            f"Found {len(unique_relays):,} unique relays in {rows_with_relays:,} rows - "
            f"Overall speed: {rows_per_second:.2f} rows/sec - "
            f"Current batch: {batch_rows_per_second:.2f} rows/sec - "
            f"DB query: {db_rows_per_second:.2f} rows/sec ({db_query_time:.2f}s) - "
            f"Memory: {current_memory:.2f} MB ({memory_change:+.2f} MB) - "
            f"Est. remaining: {estimated_remaining/60:.2f} minutes"
        )

        # Save checkpoint if we've processed enough rows since the last checkpoint
        if (
            checkpoint_interval > 0
            and total_rows - last_checkpoint >= checkpoint_interval
        ):
            print(f"Saving checkpoint at {total_rows:,} rows...")

            # Save intermediate results
            with open(temp_relays_file, "w") as f:
                for relay in sorted(unique_relays):
                    f.write(f"{relay}\n")

            with open(temp_freq_file, "w") as f:
                for relay, count in relay_counter.most_common():
                    f.write(f"{relay}: {count}\n")

            last_checkpoint = total_rows

            # Memory before garbage collection
            before_gc_memory = get_memory_usage()

            # Force garbage collection to free up memory
            gc.collect()

            # Memory after garbage collection
            after_gc_memory = get_memory_usage()
            memory_freed = before_gc_memory - after_gc_memory

            print(
                f"Checkpoint saved. Garbage collection freed {memory_freed:.2f} MB. Continuing processing..."
            )

    return unique_relays, relay_counter, total_rows, rows_with_relays


def main():
    """Main function to extract relay URLs from the database."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Extract unique relay URLs from the database."
    )
    parser.add_argument("--limit", type=int, help="Limit the number of rows to process")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch size for processing (default: 10000)",
    )
    parser.add_argument(
        "--checkpoint",
        type=int,
        default=1000000,
        help="Save intermediate results every N rows (default: 1000000, 0 to disable)",
    )
    parser.add_argument(
        "--start-id",
        type=str,
        help="Start processing from this ID (for splitting work across multiple runs)",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="",
        help="Prefix for output files (useful when running multiple instances)",
    )
    args = parser.parse_args()

    print("Connecting to database...")

    try:
        # Connect to the database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )

        # Create a cursor
        cur = conn.cursor()

        print("Connected to database. Starting extraction...")

        # If start-id is provided, use it to start from a specific point
        if args.start_id:
            print(f"Starting from ID: {args.start_id}")
            # Get the count of rows before this ID for progress calculation
            cur.execute(
                "SELECT COUNT(*) FROM raw_events WHERE tags IS NOT NULL AND id <= %s",
                (args.start_id,)
            )
            rows_before_start = cur.fetchone()[0]
            print(f"Skipping {rows_before_start:,} rows before this ID")
            
            # Modify the query to start from this ID
            cur.execute(
                "SELECT id FROM raw_events WHERE tags IS NOT NULL AND id > %s ORDER BY id LIMIT 1",
                (args.start_id,)
            )
            first_id_result = cur.fetchone()
            if first_id_result:
                first_id = first_id_result[0]
                print(f"First ID to process: {first_id}")
            else:
                print("No rows found after the specified start ID")
                return
        
        # Process data in batches
        start_time = time.time()
        unique_relays, relay_counter, total_rows, rows_with_relays = process_in_batches(
            cur,
            batch_size=args.batch_size,
            row_limit=args.limit,
            checkpoint_interval=args.checkpoint,
        )
        elapsed_time = time.time() - start_time

        # Save results to file with optional prefix
        output_file = f"{args.output_prefix}unique_relay_urls.txt"
        with open(output_file, "w") as f:
            for relay in sorted(unique_relays):
                f.write(f"{relay}\n")

        # Save frequency data to file with optional prefix
        freq_file = f"{args.output_prefix}relay_frequencies.txt"
        with open(freq_file, "w") as f:
            for relay, count in relay_counter.most_common():
                f.write(f"{relay}: {count}\n")

        # Final memory usage
        final_memory = get_memory_usage()
        print(f"Final memory usage: {final_memory:.2f} MB")

        # Print summary
        print("\nExtraction complete!")
        print(f"Total rows processed: {total_rows:,}")
        if total_rows > 0:
            print(
                f"Rows containing relay URLs: {rows_with_relays:,} ({(rows_with_relays/total_rows)*100:.2f}%)"
            )
        print(f"Unique relay URLs found: {len(unique_relays):,}")
        print(f"Top 10 most frequent relays:")
        for relay, count in relay_counter.most_common(10):
            print(f"  {relay}: {count:,}")
        print(f"\nResults saved to {output_file}")
        print(f"Frequency data saved to {freq_file}")
        print(f"Total execution time: {elapsed_time:.2f} seconds")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Close the cursor and connection
        if "cur" in locals():
            cur.close()
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    main()
