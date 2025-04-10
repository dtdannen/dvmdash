#!/usr/bin/env python3
import os
import sys
import psycopg2
import json
import time
import random
import pathlib
from collections import defaultdict, Counter
from datetime import datetime
import argparse
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("analyze_dvm_kinds")

# Load environment variables
load_dotenv()

# Database connection parameters
DB_HOST = os.getenv("PROD_POSTGRES_HOST")
DB_PORT = os.getenv("PROD_POSTGRES_PORT")
DB_NAME = os.getenv("PROD_POSTGRES_DB")
DB_USER = os.getenv("PROD_POSTGRES_USER")
DB_PASSWORD = os.getenv("PROD_POSTGRES_PASS")

# Cache directory for kind 7000 events
CACHE_DIR = os.path.join("utility", "cache", "kind_7000")

# Output directory for kind wiki pages
OUTPUT_DIR = os.path.join("docs", "kind_wiki_pages")


def get_distinct_kinds(cursor, prefix):
    """
    Get all distinct kinds with a specific prefix (e.g., '5%' or '6%').

    Args:
        cursor: Database cursor
        prefix: Kind prefix (e.g., 5 for 5xxx kinds)

    Returns:
        list: List of distinct kinds
    """
    cursor.execute(
        "SELECT DISTINCT kind FROM raw_events WHERE kind >= %s AND kind < %s ORDER BY kind",
        (prefix * 1000, (prefix + 1) * 1000),
    )
    return [row[0] for row in cursor.fetchall()]


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


def get_event_count(cursor, kind):
    """
    Get the count of events for a specific kind.

    Args:
        cursor: Database cursor
        kind: Event kind (integer)

    Returns:
        int: Number of events
    """
    cursor.execute("SELECT COUNT(*) FROM raw_events WHERE kind = %s", (kind,))
    return cursor.fetchone()[0]


def analyze_field_structure(events, kind):
    """
    Analyze the structure of fields in events.

    Args:
        events: List of event dictionaries
        kind: Event kind (integer)

    Returns:
        dict: Analysis results
    """
    total_events = len(events)
    if total_events == 0:
        return {"total_events": 0, "field_stats": {}, "tag_stats": {}, "examples": {}}

    # Track field occurrences
    field_counter = Counter()
    tag_type_counter = Counter()
    tag_structure_counter = defaultdict(Counter)

    # Track which events have which tag types
    events_with_tag_type = defaultdict(set)

    # Track examples of each field
    field_examples = {}
    tag_examples = {}

    # Process each event
    for i, event in enumerate(events):
        # Track top-level fields
        for field in event:
            field_counter[field] += 1

            # Store an example if we don't have one yet
            if field not in field_examples:
                field_examples[field] = event[field]

        # Process tags if present
        if "tags" in event:
            tags = event["tags"]
            if isinstance(tags, list):
                # Track which tag types are in this event
                event_tag_types = set()

                for tag in tags:
                    if isinstance(tag, list) and len(tag) > 0:
                        tag_type = tag[0]
                        tag_type_counter[tag_type] += 1

                        # Add this event to the set of events with this tag type
                        events_with_tag_type[tag_type].add(i)

                        # Track the structure (number of elements) for this tag type
                        tag_structure_counter[tag_type][len(tag)] += 1

                        # Store an example if we don't have one yet
                        if tag_type not in tag_examples:
                            tag_examples[tag_type] = tag

    # Calculate percentages
    field_stats = {
        field: {"count": count, "percentage": (count / total_events) * 100}
        for field, count in field_counter.items()
    }

    # Calculate tag stats based on the number of events with each tag type
    tag_stats = {
        tag_type: {
            "count": len(events_with_tag_type[tag_type]),
            "percentage": (len(events_with_tag_type[tag_type]) / total_events) * 100,
            "structures": {
                length: {
                    "count": struct_count,
                    "percentage": (struct_count / tag_type_counter[tag_type]) * 100,
                }
                for length, struct_count in tag_structure_counter[tag_type].items()
            },
        }
        for tag_type in tag_type_counter
    }

    return {
        "total_events": total_events,
        "field_stats": field_stats,
        "tag_stats": tag_stats,
        "field_examples": field_examples,
        "tag_examples": tag_examples,
    }


def process_events(cursor, kind, batch_size=5000, limit=None, max_events=100000):
    """
    Process events of a specific kind in batches.

    Args:
        cursor: Database cursor
        kind: Event kind (integer)
        batch_size: Number of events to process in each batch
        limit: Maximum number of events to process (for testing)

    Returns:
        tuple: (list of processed events, list of event IDs)
    """
    events = []
    event_ids = []
    total_count = get_event_count(cursor, kind)

    # Apply limits
    if total_count > max_events:
        logger.info(
            f"Limiting to {max_events:,} events (out of {total_count:,}) for kind {kind} due to max_events limit"
        )
        total_count = max_events

    if limit and limit < total_count:
        total_count = limit
        logger.info(
            f"Further limiting to {limit:,} events for kind {kind} due to --limit argument"
        )

    logger.info(f"Processing {total_count:,} events of kind {kind}")

    if total_count == 0:
        return events, event_ids

    processed = 0
    start_time = time.time()

    # Process in batches
    offset = 0
    while processed < total_count:
        # Adjust batch size for the last batch
        current_batch_size = min(batch_size, total_count - processed)

        # Add a random sleep to prevent hammering the database
        sleep_time = random.uniform(0.5, 2.0)
        time.sleep(sleep_time)

        # Query for a batch of events
        cursor.execute(
            """
            SELECT id, raw_data
            FROM raw_events
            WHERE kind = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (kind, current_batch_size, offset),
        )

        batch = cursor.fetchall()
        if not batch:
            break

        # Process each event in the batch
        for row in batch:
            event_id = row[0]  # Get the event ID
            raw_data = row[1]  # Get the raw JSON data
            events.append(raw_data)
            event_ids.append(event_id)

        processed += len(batch)
        offset += batch_size

        # Calculate and display progress
        elapsed_time = time.time() - start_time
        events_per_second = processed / elapsed_time if elapsed_time > 0 else 0
        estimated_remaining = (
            (total_count - processed) / events_per_second
            if events_per_second > 0
            else 0
        )

        logger.info(
            f"Processed {processed:,}/{total_count:,} events of kind {kind} "
            f"({(processed/total_count)*100:.2f}%) - "
            f"Speed: {events_per_second:.2f} events/sec - "
            f"Est. remaining: {estimated_remaining/60:.2f} minutes"
        )

    return events, event_ids


def get_cache_file_path(batch_number, batch_size):
    """
    Get the path to a cache file for a specific batch of kind 7000 events.

    Args:
        batch_number: The batch number (0-based)
        batch_size: The size of each batch

    Returns:
        str: Path to the cache file
    """
    start_offset = batch_number * batch_size
    end_offset = start_offset + batch_size - 1
    return os.path.join(
        CACHE_DIR, f"kind_7000_batch_{start_offset}_to_{end_offset}.json"
    )


def check_cache_exists(batch_number, batch_size):
    """
    Check if a cache file exists for a specific batch of kind 7000 events.

    Args:
        batch_number: The batch number (0-based)
        batch_size: The size of each batch

    Returns:
        bool: True if the cache file exists, False otherwise
    """
    cache_file = get_cache_file_path(batch_number, batch_size)
    return os.path.exists(cache_file)


def load_from_cache(batch_number, batch_size):
    """
    Load kind 7000 events from a cache file.

    Args:
        batch_number: The batch number (0-based)
        batch_size: The size of each batch

    Returns:
        list: List of events loaded from the cache file
    """
    cache_file = get_cache_file_path(batch_number, batch_size)
    try:
        with open(cache_file, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading from cache: {str(e)}")
        return None


def save_to_cache(batch_number, batch_size, events):
    """
    Save kind 7000 events to a cache file.

    Args:
        batch_number: The batch number (0-based)
        batch_size: The size of each batch
        events: List of events to save

    Returns:
        bool: True if the events were saved successfully, False otherwise
    """
    cache_file = get_cache_file_path(batch_number, batch_size)
    try:
        with open(cache_file, "w") as f:
            json.dump(events, f)
        return True
    except Exception as e:
        logger.error(f"Error saving to cache: {str(e)}")
        return False


def process_feedback_events(
    cursor, request_event_ids, batch_size=5000, limit=None, use_cache=True
):
    """
    Process feedback events (kind 7000) that reference the given request event IDs.
    This function fetches kind 7000 events in batches and filters them locally.
    It uses a cache to avoid repeatedly querying the database for the same events.

    Args:
        cursor: Database cursor
        request_event_ids: List of request event IDs to look for in the 'e' tag
        batch_size: Number of events to process in each batch
        limit: Maximum number of events to process (for testing)

    Returns:
        list: Processed feedback events
    """
    if not request_event_ids:
        logger.info("No request event IDs provided, skipping feedback events")
        return []

    # Create a set of request event IDs for faster lookups
    request_id_set = set(request_event_ids)

    # Count total number of kind 7000 events
    cursor.execute("SELECT COUNT(*) FROM raw_events WHERE kind = 7000")
    total_kind_7000 = cursor.fetchone()[0]

    logger.info(f"Found {total_kind_7000:,} total kind 7000 events")
    logger.info(f"Looking for events referencing {len(request_id_set):,} request IDs")

    # Apply limit if specified
    if limit and limit < total_kind_7000:
        total_to_check = limit
        logger.info(f"Limited to checking {limit:,} kind 7000 events")
    else:
        total_to_check = total_kind_7000

    feedback_events = []
    processed = 0
    matched = 0
    start_time = time.time()

    # Process in batches
    offset = 0
    last_db_query_time = None
    while processed < total_to_check:
        # Adjust batch size for the last batch
        current_batch_size = min(batch_size, total_to_check - processed)

        # Calculate batch number from offset
        batch_number = offset // batch_size

        # Check if this batch is already cached and use_cache is enabled
        if use_cache and check_cache_exists(batch_number, batch_size):
            logger.info(f"Loading batch {batch_number} from cache")
            batch_events = load_from_cache(batch_number, batch_size)

            if batch_events is not None:
                # Measure local processing time
                local_processing_start = time.time()

                # Filter events locally
                batch_matched = 0
                for raw_data in batch_events:
                    # Check if this event references any of our request IDs
                    if "tags" in raw_data and isinstance(raw_data["tags"], list):
                        for tag in raw_data["tags"]:
                            if (
                                isinstance(tag, list)
                                and len(tag) > 1
                                and tag[0] == "e"
                                and tag[1] in request_id_set
                            ):
                                feedback_events.append(raw_data)
                                matched += 1
                                batch_matched += 1
                                break

                local_processing_time = time.time() - local_processing_start
                local_rows_per_second = (
                    len(batch_events) / local_processing_time
                    if local_processing_time > 0
                    else 0
                )

                processed += len(batch_events)

                # Calculate and display progress
                elapsed_time = time.time() - start_time
                events_per_second = processed / elapsed_time if elapsed_time > 0 else 0
                estimated_remaining = (
                    (total_to_check - processed) / events_per_second
                    if events_per_second > 0
                    else 0
                )

                logger.info(
                    f"Checked {processed:,}/{total_to_check:,} kind 7000 events "
                    f"({(processed/total_to_check)*100:.2f}%) - "
                    f"Found {matched:,} matching events - "
                    f"Speed: {events_per_second:.2f} events/sec - "
                    f"[CACHED] Local processing: {local_rows_per_second:.2f} rows/sec ({local_processing_time:.2f}s) - "
                    f"Est. remaining: {estimated_remaining/60:.2f} minutes"
                )

                offset += batch_size
                continue

        # Add a random sleep to prevent hammering the database
        if last_db_query_time:
            sleep_time = last_db_query_time
        else:
            sleep_time = random.uniform(0.5, 2.0)

        time.sleep(sleep_time)

        # Measure database query time
        db_query_start = time.time()

        # Query for a batch of kind 7000 events
        cursor.execute(
            """
            SELECT raw_data
            FROM raw_events
            WHERE kind = 7000
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (current_batch_size, offset),
        )

        batch = cursor.fetchall()

        db_query_time = time.time() - db_query_start
        last_db_query_time = db_query_time
        db_rows_per_second = len(batch) / db_query_time if db_query_time > 0 else 0

        if not batch:
            break

        # Extract raw data from the batch
        batch_events = [row[0] for row in batch]

        # Save this batch to cache if use_cache is enabled
        if use_cache:
            logger.info(f"Saving batch {batch_number} to cache")
            save_to_cache(batch_number, batch_size, batch_events)

        # Measure local processing time
        local_processing_start = time.time()

        # Filter events locally
        batch_matched = 0
        for raw_data in batch_events:
            # Check if this event references any of our request IDs
            if "tags" in raw_data and isinstance(raw_data["tags"], list):
                for tag in raw_data["tags"]:
                    if (
                        isinstance(tag, list)
                        and len(tag) > 1
                        and tag[0] == "e"
                        and tag[1] in request_id_set
                    ):
                        feedback_events.append(raw_data)
                        matched += 1
                        batch_matched += 1
                        break

        local_processing_time = time.time() - local_processing_start
        local_rows_per_second = (
            len(batch_events) / local_processing_time
            if local_processing_time > 0
            else 0
        )

        processed += len(batch_events)
        offset += batch_size

        # Calculate and display progress
        elapsed_time = time.time() - start_time
        events_per_second = processed / elapsed_time if elapsed_time > 0 else 0
        estimated_remaining = (
            (total_to_check - processed) / events_per_second
            if events_per_second > 0
            else 0
        )

        logger.info(
            f"Checked {processed:,}/{total_to_check:,} kind 7000 events "
            f"({(processed/total_to_check)*100:.2f}%) - "
            f"Found {matched:,} matching events - "
            f"Speed: {events_per_second:.2f} events/sec - "
            f"DB query: {db_rows_per_second:.2f} rows/sec ({db_query_time:.2f}s) - "
            f"Local processing: {local_rows_per_second:.2f} rows/sec ({local_processing_time:.2f}s) - "
            f"Est. remaining: {estimated_remaining/60:.2f} minutes"
        )

        # If we've reached the limit of matching events, stop
        if limit and matched >= limit:
            logger.info(f"Reached limit of {limit:,} matching events, stopping")
            break

    logger.info(f"Found {matched:,} kind 7000 events referencing the request events")
    return feedback_events


def generate_asciidoc(
    request_kind,
    request_analysis,
    response_kind,
    response_analysis,
    feedback_analysis,
    output_file,
):
    """
    Generate an AsciiDoc file with the analysis results.

    Args:
        request_kind: Kind number for request events (5xxx), or None if no corresponding kind
        request_analysis: Analysis results for request kind, or None if no corresponding kind
        response_kind: Kind number for response events (6xxx), or None if no corresponding kind
        response_analysis: Analysis results for response kind, or None if no corresponding kind
        feedback_analysis: Analysis results for feedback events (kind 7000), or None if no feedback events
        output_file: Path to the output file
    """
    with open(output_file, "w") as f:
        # Document header
        if request_kind:
            f.write(f"= Nostr DVM Kind {request_kind}")
            if response_kind:
                f.write(f" and {response_kind}")
        else:
            f.write(f"= Nostr DVM Kind {response_kind}")
        f.write(" Analysis\n")
        f.write(":toc:\n")
        f.write(":toclevels: 3\n")
        f.write(":source-highlighter: highlight.js\n\n")

        # Introduction
        f.write("== Introduction\n\n")
        if request_kind:
            f.write(
                f"An analysis of Nostr Data Vending Machine (DVM) events of kind {request_kind}"
            )
            if response_kind:
                f.write(f" and {response_kind}")
        else:
            f.write(
                f"An analysis of Nostr Data Vending Machine (DVM) events of kind {response_kind}"
            )
        f.write(".\n")

        if request_kind:
            f.write(f"Kind {request_kind} represents DVM requests")
            if response_kind:
                f.write(
                    f", while kind {response_kind} represents the corresponding responses"
                )
        else:
            f.write(
                f"Kind {response_kind} represents DVM responses (without a corresponding request kind)"
            )
        f.write(".\n\n")

        f.write(
            "The analysis is based on data collected from the DVM network and shows the prevalence of different fields in these events.\n\n"
        )

        # Generate sections for each kind
        if request_kind and request_analysis:
            generate_kind_section(f, request_kind, request_analysis)
        if response_kind and response_analysis:
            generate_kind_section(f, response_kind, response_analysis)
        if feedback_analysis and feedback_analysis["total_events"] > 0:
            generate_kind_section(f, 7000, feedback_analysis)


def generate_kind_section(f, kind, analysis):
    """
    Generate an AsciiDoc section for a specific kind.

    Args:
        f: File handle
        kind: Event kind (integer)
        analysis: Analysis results for this kind
    """
    # Determine kind name based on the kind number
    if kind == 7000:
        kind_name = "Feedback Events"
    elif kind >= 5000 and kind < 6000:
        kind_name = f"DVM Request Events (Kind {kind})"
    elif kind >= 6000 and kind < 7000:
        kind_name = f"DVM Response Events (Kind {kind})"
    else:
        kind_name = f"Events (Kind {kind})"

    f.write(f"== Kind {kind}: {kind_name}\n\n")

    # Summary
    total_events = analysis["total_events"]
    f.write(f"=== Summary\n\n")
    f.write(f"Total events analyzed: {total_events:,}\n\n")

    if total_events == 0:
        f.write("No events found for this kind.\n\n")
        return

    # Field prevalence
    f.write("=== Field Prevalence\n\n")
    f.write('[options="header"]\n')
    f.write("|===\n")
    f.write("|Field|Percentage|Example\n")

    # Sort fields by prevalence (descending)
    sorted_fields = sorted(
        analysis["field_stats"].items(), key=lambda x: x[1]["count"], reverse=True
    )

    for field, stats in sorted_fields:
        example_value = analysis["field_examples"].get(field, "")
        # Format the example value based on its type
        if isinstance(example_value, dict) or isinstance(example_value, list):
            example_str = json.dumps(example_value, ensure_ascii=False)
            # Truncate long examples
            if len(example_str) > 50:
                example_str = example_str[:47] + "..."
        else:
            example_str = str(example_value)
            # Truncate long examples
            if len(example_str) > 50:
                example_str = example_str[:47] + "..."

        f.write(f"|{field}|{stats['percentage']:.2f}%|`{example_str}`\n")

    f.write("|===\n\n")

    # Tag analysis
    if analysis["tag_stats"]:
        f.write("=== Tag Structure Analysis\n\n")
        f.write("This section analyzes the structure of tags found in the events.\n\n")

        # Create a table for tag types
        f.write('[options="header"]\n')
        f.write("|===\n")
        f.write("|Tag Type|Percentage|Example\n")

        # Sort tag types by prevalence (descending)
        sorted_tags = sorted(
            analysis["tag_stats"].items(), key=lambda x: x[1]["count"], reverse=True
        )

        for tag_type, stats in sorted_tags:
            # Get example for this tag type
            example_tag = analysis["tag_examples"].get(tag_type, [])
            example_str = json.dumps(example_tag, ensure_ascii=False)
            if len(example_str) > 50:
                example_str = example_str[:47] + "..."

            f.write(f"|`{tag_type}`|{stats['percentage']:.2f}%|`{example_str}`\n")

        f.write("|===\n\n")

    # Complete example event (at the end of the section)
    f.write("=== Complete Example Event\n\n")

    if "id" in analysis["field_examples"]:
        example_id = analysis["field_examples"]["id"]
        f.write(f"Event with ID: `{example_id}`\n\n")

    f.write("[source,json]\n")
    f.write("----\n")

    # Construct a representative example event
    example_event = {}
    for field, value in analysis["field_examples"].items():
        example_event[field] = value

    f.write(json.dumps(example_event, indent=2))
    f.write("\n----\n\n")


def main():
    """Main function to analyze DVM events."""
    parser = argparse.ArgumentParser(
        description="Analyze Nostr DVM events of all kinds with prefixes 5xxx and 6xxx."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Batch size for processing (default: 5000)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of events to process per kind (for testing)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=OUTPUT_DIR,
        help=f"Output directory path (default: {OUTPUT_DIR})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable using cached kind 7000 events (cache is used by default)",
    )
    parser.add_argument(
        "--specific-kind",
        type=int,
        help="Process only a specific kind (e.g., 5050)",
    )
    parser.add_argument(
        "--start-kind",
        type=int,
        default=5000,
        help="Start processing from this kind number (e.g., 5050)",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=100000,
        help="Maximum number of events to process per kind (default: 100000)",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Ensure cache directory exists
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    start_time = time.time()
    logger.info("Starting DVM kinds analysis")

    # Connect to the database
    conn = connect_to_database()
    cursor = conn.cursor()

    try:
        # Get all distinct kinds with prefixes 5xxx and 6xxx
        if args.specific_kind:
            # If a specific kind is provided, only process that kind
            prefix = args.specific_kind // 1000
            if prefix not in [5, 6]:
                logger.error(
                    f"Specific kind must be 5xxx or 6xxx, got {args.specific_kind}"
                )
                return

            if prefix == 5:
                request_kinds = [args.specific_kind]
                response_kinds = []
            else:  # prefix == 6
                request_kinds = []
                response_kinds = [args.specific_kind]
        else:
            # Otherwise, get all distinct kinds
            request_kinds = get_distinct_kinds(cursor, 5)
            response_kinds = get_distinct_kinds(cursor, 6)

        logger.info(
            f"Found {len(request_kinds)} distinct request kinds (5xxx): {request_kinds}"
        )
        logger.info(
            f"Found {len(response_kinds)} distinct response kinds (6xxx): {response_kinds}"
        )

        # Check for corresponding pairs
        request_to_response = {}
        for req_kind in request_kinds:
            # The corresponding response kind would be req_kind + 1000
            resp_kind = req_kind + 1000
            if resp_kind in response_kinds:
                request_to_response[req_kind] = resp_kind
            else:
                request_to_response[req_kind] = None
                logger.warning(
                    f"Request kind {req_kind} has no corresponding response kind {resp_kind}"
                )

        # Check for response kinds without a corresponding request kind
        for resp_kind in response_kinds:
            req_kind = resp_kind - 1000
            if req_kind not in request_kinds:
                logger.warning(
                    f"Response kind {resp_kind} has no corresponding request kind {req_kind}"
                )

        # Filter request kinds based on start_kind
        if args.start_kind:
            logger.info(f"Starting from kind {args.start_kind}")
            request_to_response = {k: v for k, v in request_to_response.items() if k >= args.start_kind}
            
        # Process each request kind and its corresponding response kind (if any)
        for req_kind, resp_kind in sorted(request_to_response.items()):
            # Process request events
            logger.info(f"Processing events of kind {req_kind}")
            req_events, req_ids = process_events(
                cursor, req_kind, args.batch_size, args.limit, args.max_events
            )
            req_analysis = analyze_field_structure(req_events, req_kind)
            logger.info(
                f"Analyzed {req_analysis['total_events']:,} events of kind {req_kind}"
            )

            # Process corresponding response events (if any)
            resp_analysis = None
            if resp_kind:
                logger.info(f"Processing events of kind {resp_kind}")
                resp_events, resp_ids = process_events(
                    cursor, resp_kind, args.batch_size, args.limit, args.max_events
                )
                resp_analysis = analyze_field_structure(resp_events, resp_kind)
                logger.info(
                    f"Analyzed {resp_analysis['total_events']:,} events of kind {resp_kind}"
                )

            # Process feedback events (kind 7000) that reference request events
            logger.info(f"Processing feedback events (kind 7000) for kind {req_kind}")
            feedback_events = process_feedback_events(
                cursor, req_ids, args.batch_size, args.limit, not args.no_cache
            )
            feedback_analysis = analyze_field_structure(feedback_events, 7000)
            logger.info(
                f"Analyzed {feedback_analysis['total_events']:,} feedback events of kind 7000 for kind {req_kind}"
            )

            # Generate AsciiDoc output for this kind pair
            output_file = os.path.join(
                args.output_dir, f"kind_{req_kind}_analysis.adoc"
            )
            logger.info(f"Generating AsciiDoc output to {output_file}")
            generate_asciidoc(
                req_kind,
                req_analysis,
                resp_kind,
                resp_analysis,
                feedback_analysis,
                output_file,
            )

            logger.info(f"Results for kind {req_kind} written to {output_file}")

        # Process response kinds without a corresponding request kind
        # Filter response kinds based on start_kind
        filtered_response_kinds = [k for k in response_kinds if k >= args.start_kind]
        for resp_kind in sorted(filtered_response_kinds):
            req_kind = resp_kind - 1000
            if req_kind not in request_kinds:
                # Process response events
                logger.info(
                    f"Processing events of kind {resp_kind} (no corresponding request kind)"
                )
                resp_events, resp_ids = process_events(
                    cursor, resp_kind, args.batch_size, args.limit, args.max_events
                )
                resp_analysis = analyze_field_structure(resp_events, resp_kind)
                logger.info(
                    f"Analyzed {resp_analysis['total_events']:,} events of kind {resp_kind}"
                )

                # Generate AsciiDoc output for this response kind
                output_file = os.path.join(
                    args.output_dir, f"kind_{resp_kind}_analysis.adoc"
                )
                logger.info(f"Generating AsciiDoc output to {output_file}")
                generate_asciidoc(
                    None, None, resp_kind, resp_analysis, None, output_file
                )

                logger.info(f"Results for kind {resp_kind} written to {output_file}")

        # Log summary
        elapsed_time = time.time() - start_time
        logger.info(f"Analysis completed in {elapsed_time:.2f} seconds")
        logger.info(f"Results written to {args.output_dir}")

    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
