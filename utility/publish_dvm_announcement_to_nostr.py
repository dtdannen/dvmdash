#!/usr/bin/env python3
import os
import subprocess
import sys
import argparse
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("publish_dvm_announcement")

# Path to the DVM announcement analysis document
DEFAULT_DOC_PATH = "docs/dvm_31990_events_analysis.adoc"


def publish_dvm_announcement(file_path, relays):
    """
    Publish the DVM announcement analysis document to Nostr relays.

    Args:
        file_path: Path to the .adoc file
        relays: List of relay URLs to publish to

    Returns:
        bool: True if successful, False otherwise
    """
    # Read the file content
    try:
        with open(file_path, "r") as file:
            content = file.read()
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return False

    # Construct the d tag - using the specific tag requested by the user
    d_tag = "dvm-announcement-analysis"

    # Construct the title
    title = "Nostr DVM Announcement Events (Kind 31990) Analysis"

    # Construct the nak command
    cmd = [
        "nak",
        "event",
        "-k",
        "30818",  # Wiki article kind
        "-d",
        d_tag,
        "-t",
        f"title={title}",
        "-c",
        content,
    ] + relays

    # Execute the command, ensuring environment variables are passed
    logger.info(f"Publishing DVM announcement analysis to Nostr...")
    try:
        # Pass the current environment to the subprocess
        env = os.environ.copy()
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, env=env
        )
        logger.info("Successfully published DVM announcement analysis")
        logger.info(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error publishing DVM announcement analysis: {e}")
        logger.error(e.stderr)
        return False


def main():
    """Main function to publish the DVM announcement analysis to Nostr relays."""
    parser = argparse.ArgumentParser(
        description="Publish DVM announcement analysis to Nostr relays."
    )
    parser.add_argument(
        "--file",
        type=str,
        default=DEFAULT_DOC_PATH,
        help=f"Path to the DVM announcement analysis document (default: {DEFAULT_DOC_PATH})",
    )
    parser.add_argument(
        "--relays",
        type=str,
        nargs="+",
        default=[
            "wss://relay.primal.net",
            "wss://relay.damus.io",
            "wss://relay.wikifreedia.xyz",
        ],
        help="List of relay URLs to publish to",
    )
    args = parser.parse_args()

    # Check if NOSTR_SECRET_KEY is set in the environment
    if "NOSTR_SECRET_KEY" not in os.environ:
        logger.error("Error: NOSTR_SECRET_KEY environment variable is not set.")
        logger.error("Please set it with: export NOSTR_SECRET_KEY='nsec1...'")
        sys.exit(1)

    # Publish the document
    success = publish_dvm_announcement(args.file, args.relays)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
