#!/usr/bin/env python3
import os
import subprocess
import re
import time
import sys


def extract_title_from_adoc(content):
    """
    Extract the generated title from the adoc file content.

    Args:
        content: The content of the adoc file

    Returns:
        str: The extracted title or None if not found
    """
    # Look for the metadata comment with the generated title
    match = re.search(r"^// GENERATED_TITLE: (.+)$", content, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def publish_wiki_pages():
    # Check if NOSTR_SECRET_KEY is set in the environment
    if "NOSTR_SECRET_KEY" not in os.environ:
        print("Error: NOSTR_SECRET_KEY environment variable is not set.")
        print("Please set it with: export NOSTR_SECRET_KEY='nsec1...'")
        sys.exit(1)
    # Directory containing the AsciiDoc files
    wiki_dir = "docs/kind_wiki_pages_with_better_intros"

    # List of relay URLs to publish to
    relays = [
        "wss://relay.primal.net",
        "wss://relay.damus.io",
        "wss://relay.wikifreedia.xyz",
    ]

    # Get all AsciiDoc files in the directory
    adoc_files = [f for f in os.listdir(wiki_dir) if f.endswith(".adoc")]

    for i, file_name in enumerate(adoc_files):
        # Extract the kind number from the filename
        match = re.match(r"kind_(\d+)_analysis\.adoc", file_name)
        if match:
            kind_number = match.group(1)

            # Read the file content
            file_path = os.path.join(wiki_dir, file_name)
            with open(file_path, "r") as file:
                content = file.read()

            # Extract the generated title from the adoc file
            generated_title = extract_title_from_adoc(content)

            # Construct the d tag
            d_tag = f"kind:{kind_number}"

            # Construct the title
            # Calculate the corresponding response kind (5xxx -> 6xxx)
            response_kind = int(kind_number) + 1000

            if generated_title:
                title = (
                    f"Nostr DVM Kind {kind_number}/{response_kind} - {generated_title}"
                )
            else:
                title = f"Nostr DVM Kind {kind_number}/{response_kind}"

            # Construct the nak command
            cmd = [
                "nak",
                "event",
                "-k",
                "30818",
                "-d",
                d_tag,
                "-t",
                f"title={title}",
                "-c",
                content,
            ] + relays

            # Execute the command, ensuring environment variables are passed
            print(f"Publishing {file_name} ({i+1}/{len(adoc_files)})...")
            try:
                # Pass the current environment to the subprocess
                env = os.environ.copy()
                result = subprocess.run(
                    cmd, check=True, capture_output=True, text=True, env=env
                )
                print(f"Successfully published {file_name}")
                print(result.stdout)
            except subprocess.CalledProcessError as e:
                print(f"Error publishing {file_name}: {e}")
                print(e.stderr)

            # Add a delay between publications (except for the last one)
            if i < len(adoc_files) - 1:
                print(f"Waiting 10 seconds before publishing the next file...")
                time.sleep(10)


if __name__ == "__main__":
    publish_wiki_pages()
