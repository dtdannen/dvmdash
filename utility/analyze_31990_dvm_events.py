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
logger = logging.getLogger("analyze_31990_dvm_events")

# Load environment variables
load_dotenv()

# Database connection parameters
DB_HOST = os.getenv("PROD_POSTGRES_HOST")
DB_PORT = os.getenv("PROD_POSTGRES_PORT")
DB_NAME = os.getenv("PROD_POSTGRES_DB")
DB_USER = os.getenv("PROD_POSTGRES_USER")
DB_PASSWORD = os.getenv("PROD_POSTGRES_PASS")

# Output file for the analysis
OUTPUT_FILE = "docs/dvm_31990_events_analysis.adoc"

# DVM kind range
DVM_KIND_MIN = 5000
DVM_KIND_MAX = 5999


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


def process_31990_events(cursor, batch_size=1000, limit=None):
    """
    Process kind 31990 events in batches.

    Args:
        cursor: Database cursor
        batch_size: Number of events to process in each batch
        limit: Maximum number of events to process (for testing)

    Returns:
        list: Processed events
    """
    events = []
    total_count = get_31990_event_count(cursor)

    # Apply limit if specified
    if limit and limit < total_count:
        total_count = limit
        logger.info(f"Limited to processing {limit:,} kind 31990 events")

    logger.info(f"Processing {total_count:,} kind 31990 events")

    if total_count == 0:
        return events

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
            SELECT raw_data
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
            raw_data = row[0]  # Get the raw JSON data
            events.append(raw_data)

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

    return events


def filter_dvm_events(events):
    """
    Filter kind 31990 events to only include those related to DVM kinds (5000-5999).

    Args:
        events: List of kind 31990 events

    Returns:
        dict: Dictionary mapping DVM kind to list of events for that kind
    """
    dvm_events = defaultdict(list)
    non_dvm_count = 0

    logger.info(
        f"Filtering {len(events):,} kind 31990 events for DVM kinds ({DVM_KIND_MIN}-{DVM_KIND_MAX})"
    )

    for event in events:
        # Check if this event is related to a DVM kind
        dvm_kind = None

        # Look for DVM kind in 'd' tags
        if "tags" in event and isinstance(event["tags"], list):
            for tag in event["tags"]:
                if isinstance(tag, list) and len(tag) > 1 and tag[0] == "k":
                    try:
                        kind = int(tag[1])
                        if DVM_KIND_MIN <= kind <= DVM_KIND_MAX:
                            dvm_kind = kind
                            break
                    except (ValueError, TypeError):
                        continue

        if dvm_kind:
            dvm_events[dvm_kind].append(event)
        else:
            non_dvm_count += 1

    logger.info(
        f"Found {sum(len(events) for events in dvm_events.values()):,} events related to DVM kinds"
    )
    logger.info(f"Found {non_dvm_count:,} events not related to DVM kinds (ignored)")
    logger.info(f"Found {len(dvm_events)} distinct DVM kinds")

    return dvm_events


def analyze_field_structure(events):
    """
    Analyze the structure of fields in events.

    Args:
        events: List of event dictionaries

    Returns:
        dict: Analysis results
    """
    total_events = len(events)
    if total_events == 0:
        return {
            "total_events": 0,
            "field_stats": {},
            "tag_stats": {},
            "content_json_stats": {},
            "nip90params_stats": {},
            "field_examples": {},
            "tag_examples": {},
            "content_json_examples": {},
            "nip90params_examples": {},
        }

    # Track field occurrences
    field_counter = Counter()
    tag_type_counter = Counter()
    tag_structure_counter = defaultdict(Counter)

    # Track JSON content fields
    content_json_counter = Counter()
    content_json_examples = {}
    events_with_json_content = 0

    # Track nip90params fields
    nip90params_counter = Counter()
    nip90params_examples = {}
    events_with_nip90params = 0

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

        # Process content field if it's JSON
        if "content" in event:
            content = event["content"]
            try:
                # Try to parse content as JSON
                content_json = json.loads(content)
                if isinstance(content_json, dict):
                    events_with_json_content += 1

                    # Track JSON content fields
                    for key in content_json:
                        content_json_counter[key] += 1

                        # Store an example if we don't have one yet
                        if key not in content_json_examples:
                            content_json_examples[key] = content_json[key]

                    # Specifically analyze nip90params if present
                    if "nip90Params" in content_json:
                        nip90params_value = content_json["nip90Params"]
                        nip90params_dict = None

                        # Handle different types of nip90params values
                        if isinstance(nip90params_value, dict):
                            nip90params_dict = nip90params_value
                        elif isinstance(nip90params_value, str):
                            # Try to parse string as JSON
                            try:
                                parsed = json.loads(nip90params_value)
                                if isinstance(parsed, dict):
                                    nip90params_dict = parsed
                            except (json.JSONDecodeError, TypeError):
                                # Not valid JSON, skip
                                pass

                        # Process nip90params if we have a dictionary
                        if nip90params_dict is not None:
                            events_with_nip90params += 1

                            # Track nip90params fields
                            for param_key in nip90params_dict:
                                nip90params_counter[param_key] += 1

                                # Store an example if we don't have one yet
                                if param_key not in nip90params_examples:
                                    nip90params_examples[param_key] = nip90params_dict[
                                        param_key
                                    ]
            except (json.JSONDecodeError, TypeError):
                # Not valid JSON, skip
                pass

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

    # Calculate content JSON stats
    content_json_stats = {
        "events_with_json_content": events_with_json_content,
        "percentage_with_json_content": (
            (events_with_json_content / total_events) * 100 if total_events > 0 else 0
        ),
        "fields": {
            field: {
                "count": count,
                "percentage": (
                    (count / events_with_json_content) * 100
                    if events_with_json_content > 0
                    else 0
                ),
            }
            for field, count in content_json_counter.items()
        },
    }

    # Calculate nip90params stats
    nip90params_stats = {
        "events_with_nip90params": events_with_nip90params,
        "percentage_with_nip90params": (
            (events_with_nip90params / total_events) * 100 if total_events > 0 else 0
        ),
        "fields": {
            field: {
                "count": count,
                "percentage": (
                    (count / events_with_nip90params) * 100
                    if events_with_nip90params > 0
                    else 0
                ),
            }
            for field, count in nip90params_counter.items()
        },
    }

    return {
        "total_events": total_events,
        "field_stats": field_stats,
        "tag_stats": tag_stats,
        "content_json_stats": content_json_stats,
        "nip90params_stats": nip90params_stats,
        "field_examples": field_examples,
        "tag_examples": tag_examples,
        "content_json_examples": content_json_examples,
        "nip90params_examples": nip90params_examples,
    }


def generate_asciidoc(dvm_events, output_file):
    """
    Generate an AsciiDoc file with the analysis results.

    Args:
        dvm_events: Dictionary mapping DVM kind to list of events for that kind
        output_file: Path to the output file
    """
    with open(output_file, "w") as f:
        # Document header
        f.write("= Nostr DVM Announcement Events (Kind 31990) Analysis\n")
        f.write(":toc:\n")
        f.write(":toclevels: 3\n")
        f.write(":source-highlighter: highlight.js\n\n")

        # Introduction
        f.write("== Introduction\n\n")
        f.write(
            "This document provides an analysis of Nostr kind 31990 events related to Data Vending Machines (DVMs) that support kinds in the range 5000-5999.\n\n"
        )
        f.write(
            "Kind 31990 events are used by DVMs to announce themselves and which kinds they support, as specified in NIP-89.\n\n"
        )
        f.write(
            f"This analysis was generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n\n"
        )

        # Summary
        f.write("== Summary\n\n")
        total_events = sum(len(events) for events in dvm_events.values())
        f.write(f"Total kind 31990 events related to DVM kinds: {total_events:,}\n")
        f.write(f"Number of distinct DVM kinds: {len(dvm_events)}\n\n")

        # Table of DVM kinds
        f.write("=== DVM Kinds Overview\n\n")
        f.write('[options="header"]\n')
        f.write("|===\n")
        f.write("|DVM Kind|Number of Announcements|Percentage of Total\n")

        # Sort DVM kinds by kind number (ascending)
        sorted_dvm_kinds = sorted(dvm_events.items(), key=lambda x: x[0])

        for kind, events in sorted_dvm_kinds:
            count = len(events)
            percentage = (count / total_events) * 100 if total_events > 0 else 0
            f.write(f"|{kind}|{count:,}|{percentage:.2f}%\n")

        f.write("|===\n\n")

        # Overall field and tag analysis
        f.write("== Overall Field and Tag Analysis\n\n")
        f.write(
            "This section provides an analysis of fields and tags across all kind 31990 events related to DVM kinds.\n\n"
        )

        # Combine all events for overall analysis
        all_events = []
        for events in dvm_events.values():
            all_events.extend(events)

        overall_analysis = analyze_field_structure(all_events)

        # Field prevalence
        f.write("=== Field Prevalence\n\n")
        f.write('[options="header"]\n')
        f.write("|===\n")
        f.write("|Field|Count|Percentage|Example\n")

        # Sort fields by prevalence (descending)
        sorted_fields = sorted(
            overall_analysis["field_stats"].items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )

        for field, stats in sorted_fields:
            example_value = overall_analysis["field_examples"].get(field, "")
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

            f.write(
                f"|{field}|{stats['count']:,}|{stats['percentage']:.2f}%|`{example_str}`\n"
            )

        f.write("|===\n\n")

        # Tag analysis
        if overall_analysis["tag_stats"]:
            f.write("=== Tag Analysis\n\n")
            f.write("This section analyzes the tags found in the events.\n\n")

            # Create a table for tag types
            f.write('[options="header"]\n')
            f.write("|===\n")
            f.write("|Tag Type|Count|Percentage|Example|Common Structures\n")

            # Sort tag types by prevalence (descending)
            sorted_tags = sorted(
                overall_analysis["tag_stats"].items(),
                key=lambda x: x[1]["count"],
                reverse=True,
            )

            for tag_type, stats in sorted_tags:
                # Get example for this tag type
                example_tag = overall_analysis["tag_examples"].get(tag_type, [])
                example_str = json.dumps(example_tag, ensure_ascii=False)
                if len(example_str) > 50:
                    example_str = example_str[:47] + "..."

                # Get common structures for this tag type
                structures = stats["structures"]
                sorted_structures = sorted(
                    structures.items(), key=lambda x: x[1]["count"], reverse=True
                )
                structure_str = ", ".join(
                    f"{length} elements ({struct['percentage']:.1f}%)"
                    for length, struct in sorted_structures[:3]  # Show top 3 structures
                )

                f.write(
                    f"|`{tag_type}`|{stats['count']:,}|{stats['percentage']:.2f}%|`{example_str}`|{structure_str}\n"
                )

            f.write("|===\n\n")

        # JSON Content analysis
        content_json_stats = overall_analysis["content_json_stats"]
        if content_json_stats and content_json_stats["events_with_json_content"] > 0:
            f.write("=== JSON Content Analysis\n\n")
            f.write(
                f"This section analyzes the JSON content found in the events. {content_json_stats['events_with_json_content']:,} events ({content_json_stats['percentage_with_json_content']:.2f}%) have JSON content.\n\n"
            )

            # Create a table for JSON content fields
            f.write('[options="header"]\n')
            f.write("|===\n")
            f.write("|Field|Count|Percentage|Example\n")

            # Sort JSON content fields by prevalence (descending)
            sorted_fields = sorted(
                content_json_stats["fields"].items(),
                key=lambda x: x[1]["count"],
                reverse=True,
            )

            for field, stats in sorted_fields:
                example_value = overall_analysis["content_json_examples"].get(field, "")
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

                f.write(
                    f"|`{field}`|{stats['count']:,}|{stats['percentage']:.2f}%|`{example_str}`\n"
                )

            f.write("|===\n\n")

        # nip90params analysis
        nip90params_stats = overall_analysis["nip90params_stats"]
        if nip90params_stats and nip90params_stats["events_with_nip90params"] > 0:
            f.write("=== nip90Params Analysis\n\n")
            f.write(
                f"This section analyzes the nip90Params field within the JSON content. {nip90params_stats['events_with_nip90params']:,} events ({nip90params_stats['percentage_with_nip90params']:.2f}%) have nip90params.\n\n"
            )

            # Create a table for nip90params fields
            f.write('[options="header"]\n')
            f.write("|===\n")
            f.write("|Field|Count|Percentage|Example\n")

            # Sort nip90params fields by prevalence (descending)
            sorted_fields = sorted(
                nip90params_stats["fields"].items(),
                key=lambda x: x[1]["count"],
                reverse=True,
            )

            for field, stats in sorted_fields:
                example_value = overall_analysis["nip90params_examples"].get(field, "")
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

                f.write(
                    f"|`{field}`|{stats['count']:,}|{stats['percentage']:.2f}%|`{example_str}`\n"
                )

            f.write("|===\n\n")

        # Analysis by DVM kind
        f.write("== Analysis by DVM Kind\n\n")

        # Sort DVM kinds by kind number (ascending)
        for kind, events in sorted(dvm_events.items(), key=lambda x: x[0]):
            f.write(f"=== Kind {kind}\n\n")

            # Analyze this specific kind
            kind_analysis = analyze_field_structure(events)

            f.write(f"Number of announcements: {kind_analysis['total_events']:,}\n\n")

            # Tag analysis for this kind
            if kind_analysis["tag_stats"]:
                f.write("==== Tag Analysis\n\n")

                # Create a table for tag types
                f.write('[options="header"]\n')
                f.write("|===\n")
                f.write("|Tag Type|Count|Percentage|Example\n")

                # Sort tag types by prevalence (descending)
                sorted_tags = sorted(
                    kind_analysis["tag_stats"].items(),
                    key=lambda x: x[1]["count"],
                    reverse=True,
                )

                for tag_type, stats in sorted_tags:
                    # Get example for this tag type
                    example_tag = kind_analysis["tag_examples"].get(tag_type, [])
                    example_str = json.dumps(example_tag, ensure_ascii=False)
                    if len(example_str) > 50:
                        example_str = example_str[:47] + "..."

                    f.write(
                        f"|`{tag_type}`|{stats['count']:,}|{stats['percentage']:.2f}%|`{example_str}`\n"
                    )

                f.write("|===\n\n")

            # JSON Content analysis for this kind
            content_json_stats = kind_analysis["content_json_stats"]
            if (
                content_json_stats
                and content_json_stats["events_with_json_content"] > 0
            ):
                f.write("==== JSON Content Analysis\n\n")
                f.write(
                    f"This section analyzes the JSON content found in the events. {content_json_stats['events_with_json_content']:,} events ({content_json_stats['percentage_with_json_content']:.2f}%) have JSON content.\n\n"
                )

                # Create a table for JSON content fields
                f.write('[options="header"]\n')
                f.write("|===\n")
                f.write("|Field|Count|Percentage|Example\n")

                # Sort JSON content fields by prevalence (descending)
                sorted_fields = sorted(
                    content_json_stats["fields"].items(),
                    key=lambda x: x[1]["count"],
                    reverse=True,
                )

                for field, stats in sorted_fields:
                    example_value = kind_analysis["content_json_examples"].get(
                        field, ""
                    )
                    # Format the example value based on its type
                    if isinstance(example_value, dict) or isinstance(
                        example_value, list
                    ):
                        example_str = json.dumps(example_value, ensure_ascii=False)
                        # Truncate long examples
                        if len(example_str) > 50:
                            example_str = example_str[:47] + "..."
                    else:
                        example_str = str(example_value)
                        # Truncate long examples
                        if len(example_str) > 50:
                            example_str = example_str[:47] + "..."

                    f.write(
                        f"|`{field}`|{stats['count']:,}|{stats['percentage']:.2f}%|`{example_str}`\n"
                    )

                f.write("|===\n\n")

            # nip90params analysis for this kind
            nip90params_stats = kind_analysis["nip90params_stats"]
            f.write("==== nip90Params Analysis\n\n")
            
            if nip90params_stats and nip90params_stats["events_with_nip90params"] > 0:
                f.write(
                    f"This section analyzes the nip90Params field within the JSON content. {nip90params_stats['events_with_nip90params']:,} events ({nip90params_stats['percentage_with_nip90params']:.2f}%) have nip90Params.\n\n"
                )

                # Create a table for nip90params fields
                f.write('[options="header"]\n')
                f.write("|===\n")
                f.write("|Field|Count|Percentage|Example\n")

                # Sort nip90params fields by prevalence (descending)
                sorted_fields = sorted(
                    nip90params_stats["fields"].items(),
                    key=lambda x: x[1]["count"],
                    reverse=True,
                )

                for field, stats in sorted_fields:
                    example_value = kind_analysis["nip90params_examples"].get(field, "")
                    # Format the example value based on its type
                    if isinstance(example_value, dict) or isinstance(
                        example_value, list
                    ):
                        example_str = json.dumps(example_value, ensure_ascii=False)
                        # Truncate long examples
                        if len(example_str) > 50:
                            example_str = example_str[:47] + "..."
                    else:
                        example_str = str(example_value)
                        # Truncate long examples
                        if len(example_str) > 50:
                            example_str = example_str[:47] + "..."

                    f.write(
                        f"|`{field}`|{stats['count']:,}|{stats['percentage']:.2f}%|`{example_str}`\n"
                    )

                f.write("|===\n\n")
            else:
                f.write("No announcements for this kind contain nip90Params data.\n\n")

            # Example event
            f.write("==== Example Event\n\n")

            # Select a representative event (first one in the list)
            example_event = events[0] if events else None

            if example_event:
                if "id" in example_event:
                    example_id = example_event["id"]
                    f.write(f"Event with ID: `{example_id}`\n\n")

                f.write("[source,json]\n")
                f.write("----\n")
                f.write(json.dumps(example_event, indent=2, ensure_ascii=False))
                f.write("\n----\n\n")
            else:
                f.write("No example event available.\n\n")

    logger.info(f"AsciiDoc file generated at {output_file}")


def main():
    """Main function to analyze kind 31990 events related to DVM kinds."""
    parser = argparse.ArgumentParser(
        description="Analyze kind 31990 events related to DVM kinds (5000-5999)."
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
        "--output",
        type=str,
        default=OUTPUT_FILE,
        help=f"Output file path (default: {OUTPUT_FILE})",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    start_time = time.time()
    logger.info("Starting analysis of kind 31990 events related to DVM kinds")

    # Connect to the database
    conn = connect_to_database()
    cursor = conn.cursor()

    try:
        # Process kind 31990 events
        events = process_31990_events(cursor, args.batch_size, args.limit)

        # Filter events related to DVM kinds
        dvm_events = filter_dvm_events(events)

        # Generate AsciiDoc output
        generate_asciidoc(dvm_events, args.output)

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
