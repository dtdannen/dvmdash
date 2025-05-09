#!/usr/bin/env python3
import os
import sys
import psycopg2
import logging
from collections import OrderedDict
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("count_events_by_kind")

# Load environment variables
load_dotenv()

# Database connection parameters
DB_HOST = os.getenv("PROD_POSTGRES_HOST")
DB_PORT = os.getenv("PROD_POSTGRES_PORT")
DB_NAME = os.getenv("PROD_POSTGRES_DB")
DB_USER = os.getenv("PROD_POSTGRES_USER")
DB_PASSWORD = os.getenv("PROD_POSTGRES_PASS")

# Output file path
OUTPUT_FILE = "event_counts_by_kind.adoc"


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


def get_event_counts_by_kind(cursor):
    """
    Query the database to get counts of events per kind and the last seen timestamp.

    Args:
        cursor: Database cursor

    Returns:
        OrderedDict: Dictionary mapping kind to a dict with count and last_seen, ordered by kind
    """
    try:
        cursor.execute(
            """
            SELECT 
                kind, 
                COUNT(*) as count,
                MAX(created_at) as last_seen
            FROM raw_events 
            GROUP BY kind 
            ORDER BY kind
            """
        )
        
        # Create an ordered dictionary of kind -> {count, last_seen}
        counts = OrderedDict()
        for row in cursor.fetchall():
            kind = row[0]
            count = row[1]
            last_seen = row[2]
            counts[kind] = {"count": count, "last_seen": last_seen}
            
        return counts
    except Exception as e:
        logger.error(f"Error querying event counts: {str(e)}")
        sys.exit(1)


def get_total_event_count(cursor):
    """
    Get the total count of events in the raw_events table.

    Args:
        cursor: Database cursor

    Returns:
        int: Total number of events
    """
    try:
        cursor.execute("SELECT COUNT(*) FROM raw_events")
        return cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Error querying total event count: {str(e)}")
        sys.exit(1)


def calculate_time_since(timestamp):
    """
    Calculate the time elapsed since a given timestamp in months and days.
    
    Args:
        timestamp: The timestamp to calculate the difference from
        
    Returns:
        str: A string representing the time elapsed in months and days
    """
    if not timestamp:
        return "N/A"
    
    now = datetime.now()
    delta = now - timestamp
    
    # Calculate total days
    total_days = delta.days
    
    # Calculate months and remaining days
    months = total_days // 30  # Approximate months
    days = total_days % 30
    
    if months > 0:
        if days > 0:
            return f"{months} month{'s' if months > 1 else ''}, {days} day{'s' if days > 1 else ''} ago"
        else:
            return f"{months} month{'s' if months > 1 else ''} ago"
    elif days > 0:
        return f"{days} day{'s' if days > 1 else ''} ago"
    else:
        # Less than a day
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        else:
            minutes = (delta.seconds % 3600) // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"


def generate_adoc_table(counts, total_count, output_file):
    """
    Generate an AsciiDoc file with a table of event counts by kind.

    Args:
        counts: OrderedDict mapping kind to a dict with count and last_seen
        total_count: Total number of events
        output_file: Path to the output file
    """
    try:
        with open(output_file, "w") as f:
            # Document header
            f.write("= Nostr Event Counts by Kind\n")
            f.write(":toc:\n")
            f.write(":toclevels: 2\n")
            f.write(":source-highlighter: highlight.js\n\n")
            
            # Introduction
            f.write("== Introduction\n\n")
            f.write("This document provides a count of Nostr events by kind in the raw_events database table.\n\n")
            f.write(f"Total events in database: {total_count:,}\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Event counts table
            f.write("== Event Counts by Kind\n\n")
            f.write('[options="header"]\n')
            f.write("|===\n")
            f.write("|Kind|Count|Percentage of Total|Last Seen\n")
            
            # Add rows for each kind
            for kind, data in counts.items():
                count = data["count"]
                last_seen = data["last_seen"]
                percentage = (count / total_count) * 100 if total_count > 0 else 0
                
                # Calculate time since last seen
                time_since = calculate_time_since(last_seen)
                
                f.write(f"|{kind}|{count:,}|{percentage:.2f}%|{time_since}\n")
            
            f.write("|===\n\n")
            
            logger.info(f"AsciiDoc file generated at {output_file}")
    except Exception as e:
        logger.error(f"Error generating AsciiDoc file: {str(e)}")
        sys.exit(1)


def main():
    """Main function to count events by kind and generate AsciiDoc output."""
    logger.info("Starting event count by kind analysis")
    
    # Connect to the database
    conn = connect_to_database()
    cursor = conn.cursor()
    
    try:
        # Get total event count
        total_count = get_total_event_count(cursor)
        logger.info(f"Total events in database: {total_count:,}")
        
        # Get counts and last seen timestamps by kind
        counts = get_event_counts_by_kind(cursor)
        logger.info(f"Found {len(counts)} distinct event kinds")
        
        # Generate AsciiDoc output
        generate_adoc_table(counts, total_count, OUTPUT_FILE)
        logger.info(f"Results written to {OUTPUT_FILE}")
        
    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
