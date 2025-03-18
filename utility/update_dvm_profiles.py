#!/usr/bin/env python3
import os
import sys
import psycopg2
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
import argparse
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("update_dvm_profiles")

# Load environment variables
load_dotenv()

# Database connection parameters
# DB_HOST = os.getenv("PROD_POSTGRES_HOST", "localhost")
# DB_PORT = os.getenv("PROD_POSTGRES_PORT", "5432")
# DB_NAME = os.getenv("PROD_POSTGRES_DB", "dvmdash_pipeline")
# DB_USER = os.getenv("PROD_POSTGRES_USER", "devuser")
# DB_PASSWORD = os.getenv("PROD_POSTGRES_PASS", "devpass")

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "dvmdash_pipeline")
DB_USER = os.getenv("POSTGRES_USER", "devuser")
DB_PASSWORD = os.getenv("POSTGRES_PASS", "devpass")


def process_profile_events(batch_size=100, dry_run=False):
    """
    Process all DVM profile events (kind 31990) and update the dvms table.

    Args:
        batch_size: Number of events to process in each batch
        dry_run: If True, don't actually update the database

    Returns:
        dict: Statistics about the processing
    """
    stats = {
        "total_events": 0,
        "processed_events": 0,
        "updated_dvms": 0,
        "skipped_dvms": 0,
        "invalid_json": 0,
        "errors": 0,
    }

    try:
        # Connect to database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )

        # Create cursors for reading and writing
        read_cur = conn.cursor()
        write_cur = conn.cursor()

        # Get total count for progress reporting
        read_cur.execute("SELECT COUNT(*) FROM raw_events WHERE kind = 31990")
        total_events = read_cur.fetchone()[0]
        stats["total_events"] = total_events
        logger.info(f"Found {total_events} DVM profile events to process")

        # Process events in batches
        offset = 0
        while True:
            # Get a batch of profile events, ordered by created_at (newest first)
            read_cur.execute(
                """
                SELECT id, pubkey, created_at, content
                FROM raw_events 
                WHERE kind = 31990
                ORDER BY pubkey, created_at DESC
                LIMIT %s OFFSET %s
            """,
                (batch_size, offset),
            )

            batch = read_cur.fetchall()
            if not batch:
                break

            # Process each event in the batch
            current_dvm = None
            for event_id, pubkey, created_at, content in batch:
                stats["processed_events"] += 1

                # Skip older events for the same DVM (we only want the newest)
                if current_dvm == pubkey:
                    stats["skipped_dvms"] += 1
                    continue

                current_dvm = pubkey

                # Validate JSON content
                try:
                    profile_data = json.loads(content)

                    # Check if this DVM already has a profile and if this event is newer
                    write_cur.execute(
                        """
                        SELECT last_profile_event_id, last_profile_event_updated_at
                        FROM dvms
                        WHERE id = %s
                    """,
                        (pubkey,),
                    )

                    dvm_row = write_cur.fetchone()

                    if dvm_row:
                        existing_event_id, existing_updated_at = dvm_row

                        # Skip if we already have a newer profile
                        if existing_updated_at:
                            # Ensure both datetimes are timezone-aware for comparison
                            if not existing_updated_at.tzinfo:
                                existing_updated_at = existing_updated_at.replace(tzinfo=timezone.utc)
                            if not created_at.tzinfo:
                                created_at = created_at.replace(tzinfo=timezone.utc)
                                
                            # Compare timestamps and log details for debugging
                            if existing_updated_at >= created_at:
                                logger.debug(f"Skipping profile for DVM {pubkey}: existing={existing_updated_at} >= new={created_at}")
                                stats["skipped_dvms"] += 1
                                continue
                            else:
                                logger.debug(f"Updating profile for DVM {pubkey}: existing={existing_updated_at} < new={created_at}")

                    # Update the DVM's profile
                    if not dry_run:
                        write_cur.execute(
                            """
                            INSERT INTO dvms (
                                id, first_seen, last_seen, 
                                last_profile_event_id, last_profile_event_raw_json, 
                                last_profile_event_updated_at, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (id) DO UPDATE SET
                                last_profile_event_id = %s,
                                last_profile_event_raw_json = %s,
                                last_profile_event_updated_at = %s,
                                updated_at = CURRENT_TIMESTAMP
                        """,
                            (
                                pubkey,
                                created_at,
                                created_at,
                                event_id,
                                content,
                                created_at,
                                event_id,
                                content,
                                created_at,
                            ),
                        )

                    stats["updated_dvms"] += 1

                except json.JSONDecodeError:
                    logger.warning(
                        f"Invalid JSON content in event {event_id} for DVM {pubkey}"
                    )
                    stats["invalid_json"] += 1
                except Exception as e:
                    logger.error(f"Error processing event {event_id}: {str(e)}")
                    stats["errors"] += 1

            # Commit the batch
            if not dry_run:
                conn.commit()

            # Update offset for next batch
            offset += batch_size

            # Log progress
            progress = min(
                100, round((stats["processed_events"] / total_events) * 100, 2)
            )
            logger.info(
                f"Progress: {progress}% - Processed {stats['processed_events']}/{total_events} events"
            )

        return stats

    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        stats["errors"] += 1
        return stats
    finally:
        if "conn" in locals():
            conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Update DVM profiles from kind 31990 events"
    )
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Batch size for processing"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually update the database"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    start_time = time.time()
    logger.info("Starting DVM profile update process")

    stats = process_profile_events(batch_size=args.batch_size, dry_run=args.dry_run)

    # Log summary
    duration = time.time() - start_time
    logger.info(f"Process completed in {duration:.2f} seconds")
    logger.info(f"Total events: {stats['total_events']}")
    logger.info(f"Processed events: {stats['processed_events']}")
    logger.info(f"Updated DVMs: {stats['updated_dvms']}")
    logger.info(f"Skipped DVMs: {stats['skipped_dvms']}")
    logger.info(f"Invalid JSON: {stats['invalid_json']}")
    logger.info(f"Errors: {stats['errors']}")

    if args.dry_run:
        logger.info("DRY RUN - No database changes were made")


if __name__ == "__main__":
    main()
