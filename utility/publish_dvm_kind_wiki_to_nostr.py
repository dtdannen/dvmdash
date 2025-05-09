#!/usr/bin/env python3
import os
import subprocess
import re
import time
import sys
import argparse


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


def publish_wiki_article(file_path, relays, total=1, current=1):
    """
    Publish a single wiki article to Nostr relays.
    
    Args:
        file_path: Path to the .adoc file
        relays: List of relay URLs to publish to
        total: Total number of articles being published (for progress display)
        current: Current article number (for progress display)
        
    Returns:
        bool: True if successful, False otherwise
    """
    file_name = os.path.basename(file_path)
    
    # Extract the kind number from the filename
    match = re.match(r"kind_(\d+)_analysis\.adoc", file_name)
    if not match:
        print(f"Error: File {file_name} does not match the expected naming pattern.")
        return False
        
    kind_number = match.group(1)
    
    # Read the file content
    try:
        with open(file_path, "r") as file:
            content = file.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return False

    # Extract the generated title from the adoc file
    generated_title = extract_title_from_adoc(content)

    # Construct the d tag
    d_tag = f"kind:{kind_number}"

    # Construct the title
    # Calculate the corresponding response kind (5xxx -> 6xxx)
    response_kind = int(kind_number) + 1000

    if generated_title:
        title = f"Nostr DVM Kind {kind_number}/{response_kind} - {generated_title}"
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
    print(f"Publishing {file_name} ({current}/{total})...")
    try:
        # Pass the current environment to the subprocess
        env = os.environ.copy()
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, env=env
        )
        print(f"Successfully published {file_name}")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error publishing {file_name}: {e}")
        print(e.stderr)
        return False


def publish_wiki_pages(kind_number=None):
    """
    Publish wiki pages to Nostr relays.
    
    Args:
        kind_number: Optional kind number to publish a specific article.
                     If None, all articles will be published.
    """
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
    
    if kind_number:
        # Find the specific file for the requested kind
        target_file = f"kind_{kind_number}_analysis.adoc"
        if target_file not in adoc_files:
            print(f"Error: No wiki article found for kind {kind_number}.")
            print(f"Available kinds: {', '.join(sorted([re.match(r'kind_(\d+)_analysis\.adoc', f).group(1) for f in adoc_files if re.match(r'kind_(\d+)_analysis\.adoc', f)]))}")
            sys.exit(1)
            
        # Publish just the one article
        file_path = os.path.join(wiki_dir, target_file)
        success = publish_wiki_article(file_path, relays)
        if not success:
            sys.exit(1)
    else:
        # Publish all articles
        for i, file_name in enumerate(adoc_files):
            file_path = os.path.join(wiki_dir, file_name)
            success = publish_wiki_article(file_path, relays, len(adoc_files), i+1)
            
            # Add a delay between publications (except for the last one)
            if i < len(adoc_files) - 1 and success:
                print(f"Waiting 10 seconds before publishing the next file...")
                time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description="Publish Nostr DVM wiki articles to Nostr relays.")
    parser.add_argument("--kind", type=str, help="Specific kind number to publish (e.g., 5314). If not provided, all articles will be published.")
    args = parser.parse_args()
    
    publish_wiki_pages(args.kind)


if __name__ == "__main__":
    main()
