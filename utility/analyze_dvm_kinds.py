#!/usr/bin/env python3
import os
import sys
import psycopg2
import json
import time
import random
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


def process_events(cursor, kind, batch_size=5000, limit=None):
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

    if limit and limit < total_count:
        total_count = limit
        logger.info(f"Limited to processing {limit:,} events of kind {kind}")
    else:
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


def process_feedback_events(cursor, request_event_ids, batch_size=5000, limit=None):
    """
    Process feedback events (kind 7000) that reference the given request event IDs.
    This function fetches kind 7000 events in batches and filters them locally.

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

        # Measure local processing time
        local_processing_start = time.time()

        # Filter events locally
        batch_matched = 0
        for row in batch:
            raw_data = row[0]  # Get the raw JSON data

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
            len(batch) / local_processing_time if local_processing_time > 0 else 0
        )

        processed += len(batch)
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
    kind_5050_analysis, kind_6050_analysis, kind_7000_analysis, output_file
):
    """
    Generate an AsciiDoc file with the analysis results.

    Args:
        kind_5050_analysis: Analysis results for kind 5050
        kind_6050_analysis: Analysis results for kind 6050
        kind_7000_analysis: Analysis results for kind 7000
        output_file: Path to the output file
    """
    with open(output_file, "w") as f:
        # Document header
        f.write("= Nostr DVM Kind 5050 and 6050 Analysis\n")
        f.write(":toc:\n")
        f.write(":toclevels: 3\n")
        f.write(":source-highlighter: highlight.js\n\n")

        # Introduction
        f.write("== Introduction\n\n")
        f.write(
            "This document provides an analysis of Nostr Data Vending Machine (DVM) events of kinds 5050 and 6050.\n"
        )
        f.write(
            "Kind 5050 represents text generation requests, while kind 6050 represents the corresponding responses.\n\n"
        )
        f.write(
            "The analysis is based on data collected from the DVM network and shows the prevalence of different fields in these events.\n\n"
        )

        # Generate sections for each kind
        generate_kind_section(f, 5050, kind_5050_analysis)
        generate_kind_section(f, 6050, kind_6050_analysis)
        generate_kind_section(f, 7000, kind_7000_analysis)


def generate_kind_section(f, kind, analysis):
    """
    Generate an AsciiDoc section for a specific kind.

    Args:
        f: File handle
        kind: Event kind (integer)
        analysis: Analysis results for this kind
    """
    kind_name = (
        "Text Generation Requests"
        if kind == 5050
        else ("Text Generation Responses" if kind == 6050 else "Feedback Events")
    )

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
        description="Analyze Nostr DVM events of kinds 5050 and 6050."
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
        "--output",
        type=str,
        default="dvm_kinds_analysis.adoc",
        help="Output file path (default: dvm_kinds_analysis.adoc)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    start_time = time.time()
    logger.info("Starting DVM kinds analysis")

    # Connect to the database
    conn = connect_to_database()
    cursor = conn.cursor()

    try:
        # Process events of kind 5050
        logger.info("Processing events of kind 5050")
        kind_5050_events, kind_5050_ids = process_events(
            cursor, 5050, args.batch_size, args.limit
        )
        kind_5050_analysis = analyze_field_structure(kind_5050_events, 5050)
        logger.info(
            f"Analyzed {kind_5050_analysis['total_events']:,} events of kind 5050"
        )

        # Process events of kind 6050
        logger.info("Processing events of kind 6050")
        kind_6050_events, kind_6050_ids = process_events(
            cursor, 6050, args.batch_size, args.limit
        )
        kind_6050_analysis = analyze_field_structure(kind_6050_events, 6050)
        logger.info(
            f"Analyzed {kind_6050_analysis['total_events']:,} events of kind 6050"
        )

        # Process feedback events (kind 7000) that reference kind 5050 events
        logger.info("Processing feedback events (kind 7000)")
        kind_7000_events = process_feedback_events(
            cursor, kind_5050_ids, args.batch_size, args.limit
        )
        kind_7000_analysis = analyze_field_structure(kind_7000_events, 7000)
        logger.info(
            f"Analyzed {kind_7000_analysis['total_events']:,} feedback events of kind 7000"
        )

        # Generate AsciiDoc output
        logger.info(f"Generating AsciiDoc output to {args.output}")
        generate_asciidoc(
            kind_5050_analysis, kind_6050_analysis, kind_7000_analysis, args.output
        )

        # Log summary
        elapsed_time = time.time() - start_time
        logger.info(f"Analysis completed in {elapsed_time:.2f} seconds")
        logger.info(f"Results written to {args.output}")

    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
