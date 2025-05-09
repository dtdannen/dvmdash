#!/usr/bin/env python3
import os
import sys
import psycopg2
import logging
import time
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("count_raw_events")

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


def count_raw_events(cursor):
    """
    Count the total number of rows in the raw_events table.

    Args:
        cursor: Database cursor

    Returns:
        int: Total number of rows
    """
    try:
        logger.info("Counting rows in raw_events table (this may take a while for large tables)...")
        start_time = time.time()
        
        cursor.execute("SELECT COUNT(*) FROM raw_events")
        count = cursor.fetchone()[0]
        
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info(f"Count completed in {duration:.2f} seconds")
        return count
    except Exception as e:
        logger.error(f"Error counting rows: {str(e)}")
        sys.exit(1)


def main():
    """Main function to count rows in raw_events table."""
    logger.info("Starting raw_events row count")
    
    # Connect to the database
    conn = connect_to_database()
    cursor = conn.cursor()
    
    try:
        # Count rows
        count = count_raw_events(cursor)
        logger.info(f"Total rows in raw_events table: {count:,}")
        print(f"\nTotal rows in raw_events table: {count:,}\n")
        
    except Exception as e:
        logger.error(f"Error during counting: {str(e)}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
