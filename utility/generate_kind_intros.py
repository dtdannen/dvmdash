"""
Script to generate improved introductions for DVM kind wiki pages.

This script:
1. Makes a call to Claude via the Anthropic API
2. Reads a page describing a specific kind number (e.g., https://www.data-vending-machines.org/kinds/5000/)
3. Looks at the existing adoc file for that kind
4. Writes 3 specific sentences for the beginning of an intro to the wiki pages

The three sentences describe:
1. What the kind job type is
2. What the input looks like
3. What the output looks like
"""

import os
import sys
import requests
import anthropic
import re
import psycopg2
import json
from bs4 import BeautifulSoup
from pathlib import Path
import argparse
import logging
from dotenv import load_dotenv


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("generate_kind_intros")

# Load environment variables from .env file
load_dotenv(verbose=True)

# Debug environment variables
logger.info("Environment variables:")
logger.info(
    f"ANTHROPIC_API_KEY set: {'Yes' if os.environ.get('ANTHROPIC_API_KEY') else 'No'}"
)

# Constants
SOURCE_DIR = Path("docs/kind_wiki_pages")
TARGET_DIR = Path("docs/kind_wiki_pages_with_better_intros")
KIND_URL_TEMPLATE = "https://www.data-vending-machines.org/kinds/{kind}/"

# Database connection parameters - these will be loaded from environment variables
DB_HOST = os.getenv("PROD_POSTGRES_HOST")
DB_PORT = os.getenv("PROD_POSTGRES_PORT")
DB_NAME = os.getenv("PROD_POSTGRES_DB")
DB_USER = os.getenv("PROD_POSTGRES_USER")
DB_PASSWORD = os.getenv("PROD_POSTGRES_PASS")


def fetch_examples_from_db(kind_number):
    """
    Fetch example requests and responses from the database for a specific kind number.

    Args:
        kind_number: The kind number to fetch examples for

    Returns:
        tuple: (success, request_examples, response_examples) where success is a boolean
               and request_examples and response_examples are strings containing JSON examples
    """
    logger.info(f"Fetching examples from database for kind {kind_number}")

    # Check if database connection parameters are set
    if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
        logger.error("Database connection parameters not set")
        return (
            False,
            "Database connection parameters not set",
            "Database connection parameters not set",
        )

    try:
        # Connect to the database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        cursor = conn.cursor()

        # Fetch request examples (kind 5xxx)
        request_kind = kind_number
        cursor.execute(
            """
            SELECT raw_data
            FROM raw_events
            WHERE kind = %s
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (request_kind,),
        )
        request_rows = cursor.fetchall()

        # Fetch response examples (kind 6xxx)
        response_kind = kind_number + 1000  # Convert 5xxx to 6xxx
        cursor.execute(
            """
            SELECT raw_data
            FROM raw_events
            WHERE kind = %s
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (response_kind,),
        )
        response_rows = cursor.fetchall()

        # Close the database connection
        cursor.close()
        conn.close()

        # Format the examples as JSON strings
        request_examples = []
        for row in request_rows:
            try:
                # Pretty print the JSON
                event = row[0]
                request_examples.append(json.dumps(event, indent=2))
            except Exception as e:
                logger.warning(f"Error formatting request example: {str(e)}")

        response_examples = []
        for row in response_rows:
            try:
                # Pretty print the JSON
                event = row[0]
                response_examples.append(json.dumps(event, indent=2))
            except Exception as e:
                logger.warning(f"Error formatting response example: {str(e)}")

        # Join the examples with newlines
        request_examples_str = "\n\n".join(request_examples)
        response_examples_str = "\n\n".join(response_examples)

        logger.info(
            f"Successfully fetched {len(request_examples)} request examples and {len(response_examples)} response examples"
        )
        return True, request_examples_str, response_examples_str

    except Exception as e:
        logger.error(f"Error fetching examples from database: {str(e)}")
        return False, f"Error: {str(e)}", f"Error: {str(e)}"


def fetch_kind_webpage(kind_number):
    """
    Fetch the webpage for a specific kind number if it exists.

    Args:
        kind_number: The kind number to fetch

    Returns:
        tuple: (success, content) where success is a boolean and content is the page content or error message
    """
    url = KIND_URL_TEMPLATE.format(kind=kind_number)
    logger.info(f"Fetching webpage for kind {kind_number} from {url}")

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            logger.info(f"Successfully fetched webpage for kind {kind_number}")
            # Parse with BeautifulSoup to get clean text
            soup = BeautifulSoup(response.text, "html.parser")
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
            # Get text
            text = soup.get_text()
            # Break into lines and remove leading and trailing space on each
            lines = (line.strip() for line in text.splitlines())
            # Break multi-headlines into a line each
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            # Drop blank lines
            text = "\n".join(chunk for chunk in chunks if chunk)
            return True, text
        else:
            logger.warning(
                f"Failed to fetch webpage for kind {kind_number}: HTTP {response.status_code}"
            )
            return False, f"HTTP Error: {response.status_code}"
    except Exception as e:
        logger.error(f"Error fetching webpage for kind {kind_number}: {str(e)}")
        return False, f"Error: {str(e)}"


def read_existing_adoc(kind_number):
    """
    Read the existing adoc file for a specific kind number.

    Args:
        kind_number: The kind number to read

    Returns:
        tuple: (success, content) where success is a boolean and content is the file content or error message
    """
    file_path = SOURCE_DIR / f"kind_{kind_number}_analysis.adoc"
    logger.info(f"Reading existing adoc file from {file_path}")

    try:
        if file_path.exists():
            with open(file_path, "r") as f:
                content = f.read()
            logger.info(f"Successfully read existing adoc file for kind {kind_number}")
            return True, content
        else:
            logger.warning(f"Adoc file for kind {kind_number} not found at {file_path}")
            return False, f"File not found: {file_path}"
    except Exception as e:
        logger.error(f"Error reading adoc file for kind {kind_number}: {str(e)}")
        return False, f"Error: {str(e)}"


def generate_title_with_claude(
    kind_number, webpage_content, adoc_content, intro_sentences=None
):
    """
    Use Claude to generate a concise 2-4 word title for the kind.

    Args:
        kind_number: The kind number
        webpage_content: Content from the kind's webpage (or None if not available)
        adoc_content: Content from the existing adoc file
        intro_sentences: List of 3 intro sentences (if already generated)

    Returns:
        tuple: (success, title) where success is a boolean and title is a string or error message
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        logger.error(
            "Please set this environment variable in your .env file or directly in your environment"
        )
        logger.error("Example: export ANTHROPIC_API_KEY='your-api-key-here'")
        return False, "ANTHROPIC_API_KEY environment variable not set"

    logger.info(f"Generating title for kind {kind_number} using Claude")

    # Create the client
    client = anthropic.Anthropic(api_key=api_key)

    # Prepare the prompt
    prompt = f"""
You are helping to create concise titles for Data Vending Machine (DVM) kind wiki pages.

I need you to generate a very short, descriptive title (2-4 words only) that captures the essence of DVM kind {kind_number}.

Here is the existing documentation for kind {kind_number}:

```
{adoc_content}
```
"""

    # Add intro sentences if available
    if intro_sentences and len(intro_sentences) == 3:
        intro_text = " ".join(intro_sentences)
        prompt += f"""
I've also generated the following introduction for this kind, which you should use as a primary source for creating the title:

```
{intro_text}
```
"""

    # Add webpage content if available
    if webpage_content:
        prompt += f"""
Additionally, here is the content from the webpage describing kind {kind_number}, its a good idea to reuse the title here if it's consistent with the intro paragraph:

```
{webpage_content}
```
"""
    else:
        # Since we don't have any existing documentation, let's get more examples and ask Claude to guess for us
        logger.info(
            f"No webpage documentation found for kind {kind_number}, fetching examples from database"
        )
        db_success, request_examples, response_examples = fetch_examples_from_db(
            kind_number
        )

        if db_success and request_examples and response_examples:
            prompt += f"""
There does not exist documentation yet for this DVM job type. Can you help me create a title based on these requests (kind {kind_number}) and responses (kind {kind_number + 1000})? Please make an estimated guess as best you can.

Request Examples:
```json
{request_examples}
```

Response Examples:
```json
{response_examples}
```
"""
        else:
            logger.warning(
                f"Failed to fetch examples from database for kind {kind_number}"
            )

    prompt += """
Based on this information, please generate a concise, descriptive title that is ONLY 2-4 words long. The title should capture the essence of what this DVM kind does.

IMPORTANT: Do NOT include the word "Request" in the title, as we already know these are requests because they are DVM Kinds.

Format your response as:

Title: [Your 2-4 word title here]

Do not include any other text in your response.
"""

    try:
        # Make the API call
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=100,
            temperature=0.2,
            system="You are a helpful assistant that creates concise, descriptive titles.",
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the title from the response
        content = response.content[0].text
        logger.info(f"Received response from Claude")

        # Parse the title using regex
        pattern = r"Title: (.*)"
        match = re.search(pattern, content)

        if match:
            title = match.group(1).strip()
            # Verify the title is 2-4 words
            word_count = len(title.split())
            if 2 <= word_count <= 4:
                logger.info(
                    f"Successfully extracted title from Claude's response: '{title}'"
                )
                return True, title
            else:
                logger.warning(
                    f"Title '{title}' has {word_count} words, expected 2-4 words"
                )
                # Try to truncate or expand if needed
                if word_count > 4:
                    # Take first 4 words
                    title = " ".join(title.split()[:4])
                    logger.info(f"Truncated title to 4 words: '{title}'")
                    return True, title
                elif word_count == 1:
                    # Use as is, even though it's only one word
                    logger.info(f"Using single-word title: '{title}'")
                    return True, title

        # If we get here, we couldn't extract a valid title
        logger.error(
            f"Could not extract a valid title from Claude's response: {content}"
        )
        # Fallback to a generic title
        fallback_title = f"Kind {kind_number} Service"
        logger.info(f"Using fallback title: '{fallback_title}'")
        return True, fallback_title

    except Exception as e:
        logger.error(f"Error calling Claude API: {str(e)}")
        return False, f"Error calling Claude API: {str(e)}"


def generate_intro_with_claude(kind_number, webpage_content, adoc_content):
    """
    Use Claude to generate 3 intro sentences based on the kind info.

    Args:
        kind_number: The kind number
        webpage_content: Content from the kind's webpage (or None if not available)
        adoc_content: Content from the existing adoc file

    Returns:
        tuple: (success, sentences) where success is a boolean and sentences is a list of 3 sentences or error message
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        logger.error(
            "Please set this environment variable in your .env file or directly in your environment"
        )
        logger.error("Example: export ANTHROPIC_API_KEY='your-api-key-here'")
        return False, "ANTHROPIC_API_KEY environment variable not set"

    logger.info(f"Generating intro sentences for kind {kind_number} using Claude")

    # Create the client
    client = anthropic.Anthropic(api_key=api_key)

    # Prepare the prompt
    prompt = f"""
You are helping to write improved introductions for Data Vending Machine (DVM) kind wiki pages.

I need you to write exactly 3 sentences that will form the beginning of an introduction to a wiki page about DVM kind {kind_number}:

1. An opening sentence that describes what the kind job type is
2. A sentence that describes what the input looks like
3. A sentence that describes what the output looks like

These sentences will be read by humans, especially those new to the DVM ecosystem.

Here is the existing documentation for kind {kind_number}:

```
{adoc_content}
```
"""

    # Add webpage content if available
    if webpage_content:
        prompt += f"""
Additionally, here is the content from the webpage describing kind {kind_number}:

```
{webpage_content}
```
"""
    else:
        # Since we don't have any existing documentation, let's get more examples and ask Claude to guess for us
        logger.info(
            f"No webpage documentation found for kind {kind_number}, fetching examples from database"
        )
        db_success, request_examples, response_examples = fetch_examples_from_db(
            kind_number
        )

        if db_success and request_examples and response_examples:
            prompt += f"""
There does not exist documentation yet for this DVM job type. Can you help me guess what the job might be doing based on these requests (kind {kind_number}) and responses (kind {kind_number + 1000})? Please make an estimated guess as best you can. This intro is only a starting point for humans to understand what this job type seems to be doing.

Request Examples:
```json
{request_examples}
```

Response Examples:
```json
{response_examples}
```
"""
        else:
            logger.warning(
                f"Failed to fetch examples from database for kind {kind_number}"
            )

    prompt += """
Based on this information, please write exactly 3 sentences as described above. Format your response as:

Sentence 1: [Your first sentence here]
Sentence 2: [Your second sentence here]
Sentence 3: [Your third sentence here]

Do not include any other text in your response.
"""

    try:
        # Make the API call
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            temperature=0.2,
            system="You are a helpful assistant that writes clear, concise documentation.",
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the sentences from the response
        content = response.content[0].text
        logger.info(f"Received response from Claude")

        # Parse the sentences using regex
        pattern = r"Sentence \d+: (.*)"
        sentences = re.findall(pattern, content)

        if len(sentences) == 3:
            logger.info(f"Successfully extracted 3 sentences from Claude's response")
            return True, sentences
        else:
            logger.warning(
                f"Failed to extract exactly 3 sentences from Claude's response. Found {len(sentences)} sentences."
            )
            # Try to extract sentences another way
            lines = content.strip().split("\n")
            if len(lines) >= 3:
                # Just take the first 3 non-empty lines
                sentences = [line for line in lines if line.strip()][:3]
                if len(sentences) == 3:
                    logger.info(f"Extracted 3 sentences using fallback method")
                    return True, sentences

            logger.error(
                f"Could not extract 3 sentences from Claude's response: {content}"
            )
            return (
                False,
                f"Could not extract 3 sentences from Claude's response: {content}",
            )

    except Exception as e:
        logger.error(f"Error calling Claude API: {str(e)}")
        return False, f"Error calling Claude API: {str(e)}"


def create_improved_adoc(kind_number, original_adoc, intro_sentences, title):
    """
    Create a new adoc file with the improved intro and title.

    Args:
        kind_number: The kind number
        original_adoc: Content of the original adoc file
        intro_sentences: List of 3 intro sentences
        title: The generated title for the kind

    Returns:
        tuple: (success, message) where success is a boolean and message is a success or error message
    """
    target_file = TARGET_DIR / f"kind_{kind_number}_analysis.adoc"
    logger.info(f"Creating improved adoc file at {target_file}")

    try:
        # Find the Introduction section
        intro_match = re.search(
            r"== Introduction\n\n(.*?)(?=\n\n==|\Z)", original_adoc, re.DOTALL
        )
        if not intro_match:
            logger.warning(
                f"Could not find Introduction section in original adoc file for kind {kind_number}"
            )
            return False, "Could not find Introduction section in original adoc file"

        # Create the new intro section
        new_intro = "== Introduction\n\n"
        new_intro += (
            intro_sentences[0]
            + " "
            + intro_sentences[1]
            + " "
            + intro_sentences[2]
            + "\n\n"
        )

        # Add a header after the new intro sentences
        new_intro += "=== Analysis\n\n"

        # Add the original intro content after our new sentences and the header, with DVMDash attribution
        original_intro = intro_match.group(1).strip()

        # Replace the standard analysis description with one that includes DVMDash attribution
        dvmdash_attribution = "The analysis is based on data collected from the DVM network by [DVMDash](https://dvmdash.live), an online monitoring and debugging platform, and shows the prevalence of different fields in these events."
        modified_intro = re.sub(
            r"The analysis is based on data collected from the DVM network and shows the prevalence of different fields in these events\.",
            dvmdash_attribution,
            original_intro,
        )

        new_intro += modified_intro + "\n\n"

        # Replace the original intro with our new intro
        new_adoc = original_adoc.replace(intro_match.group(0), new_intro.strip())

        # Update the title format and add the generated title
        title_match = re.search(
            r"^= Nostr DVM Kind (\d+)( and (\d+))? Analysis", new_adoc
        )
        if title_match:
            if title_match.group(3):  # If there's a second kind number
                new_title = f"= Nostr DVM Kind {title_match.group(1)}/{title_match.group(3)} - {title}"
            else:
                # Check if it's a 5xxx or 6xxx kind
                kind_prefix = int(title_match.group(1)) // 1000
                new_title = f"= Nostr DVM Kind {kind_prefix}xxx - {title}"

            new_adoc = re.sub(
                r"^= Nostr DVM Kind (\d+)( and (\d+))? Analysis", new_title, new_adoc
            )

        # Add a metadata comment with the title for easy extraction by other scripts
        new_adoc = f"// GENERATED_TITLE: {title}\n{new_adoc}"

        # Write the new file
        with open(target_file, "w") as f:
            f.write(new_adoc)

        logger.info(f"Successfully created improved adoc file for kind {kind_number}")
        return True, f"Successfully created improved adoc file at {target_file}"

    except Exception as e:
        logger.error(
            f"Error creating improved adoc file for kind {kind_number}: {str(e)}"
        )
        return False, f"Error creating improved adoc file: {str(e)}"


def process_kind(kind_number):
    """
    Process a single kind number.

    Args:
        kind_number: The kind number to process

    Returns:
        bool: True if successful, False otherwise
    """
    # Read the existing adoc file
    adoc_success, adoc_content = read_existing_adoc(kind_number)
    if not adoc_success:
        logger.error(f"Failed to read existing adoc file: {adoc_content}")
        return False

    # Fetch the kind webpage if it exists
    web_success, webpage_content = fetch_kind_webpage(kind_number)
    if not web_success:
        logger.warning(
            f"Could not fetch webpage for kind {kind_number}: {webpage_content}"
        )
        webpage_content = None  # We'll proceed without the webpage content

    # Generate the intro sentences using Claude first
    intro_success, intro_sentences = generate_intro_with_claude(
        kind_number, webpage_content, adoc_content
    )
    if not intro_success:
        logger.error(f"Failed to generate intro sentences: {intro_sentences}")
        return False

    # Now generate a title using Claude, passing in the intro sentences
    title_success, title = generate_title_with_claude(
        kind_number, webpage_content, adoc_content, intro_sentences
    )
    if not title_success:
        logger.error(f"Failed to generate title: {title}")
        title = f"Kind {kind_number} Service"  # Fallback title
        logger.info(f"Using fallback title: '{title}'")

    # Create the improved adoc file with title
    create_success, create_message = create_improved_adoc(
        kind_number, adoc_content, intro_sentences, title
    )
    if not create_success:
        logger.error(f"Failed to create improved adoc file: {create_message}")
        return False

    logger.info(f"Successfully generated improved intro for kind {kind_number}")
    logger.info(f"Generated title: '{title}'")
    logger.info(f"New sentences:")
    for i, sentence in enumerate(intro_sentences, 1):
        logger.info(f"  {i}. {sentence}")

    logger.info(f"Output file: {TARGET_DIR / f'kind_{kind_number}_analysis.adoc'}")
    return True


def main():
    """Main function to generate improved intros for DVM kind wiki pages."""
    parser = argparse.ArgumentParser(
        description="Generate improved introductions for DVM kind wiki pages."
    )
    parser.add_argument(
        "--kind",
        type=int,
        help="The specific kind number to process (e.g., 5000)",
        default=None,
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all kinds in the docs/kind_wiki_pages directory",
    )
    args = parser.parse_args()

    # Ensure target directory exists
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    if args.kind:
        # Process a single kind
        logger.info(f"Processing kind {args.kind}")
        process_kind(args.kind)
    elif args.all:
        # Process all kinds
        logger.info("Processing all kinds in docs/kind_wiki_pages directory")

        # Get all adoc files in the source directory
        adoc_files = list(SOURCE_DIR.glob("kind_*_analysis.adoc"))
        logger.info(f"Found {len(adoc_files)} adoc files")

        # Extract kind numbers from filenames
        kind_numbers = []
        for file_path in adoc_files:
            match = re.search(r"kind_(\d+)_analysis\.adoc", file_path.name)
            if match:
                kind_numbers.append(int(match.group(1)))

        logger.info(f"Extracted {len(kind_numbers)} kind numbers: {kind_numbers}")

        # Process each kind
        success_count = 0
        for kind_number in sorted(kind_numbers):
            logger.info(f"Processing kind {kind_number}")
            if process_kind(kind_number):
                success_count += 1

        logger.info(
            f"Successfully processed {success_count} out of {len(kind_numbers)} kinds"
        )
    else:
        # No arguments provided, default to processing all kinds
        logger.info("No arguments provided, processing all kinds")

        # Get all adoc files in the source directory
        adoc_files = list(SOURCE_DIR.glob("kind_*_analysis.adoc"))
        logger.info(f"Found {len(adoc_files)} adoc files")

        # Extract kind numbers from filenames
        kind_numbers = []
        for file_path in adoc_files:
            match = re.search(r"kind_(\d+)_analysis\.adoc", file_path.name)
            if match:
                kind_numbers.append(int(match.group(1)))

        logger.info(f"Extracted {len(kind_numbers)} kind numbers: {kind_numbers}")

        # Process each kind
        success_count = 0
        for kind_number in sorted(kind_numbers):
            logger.info(f"Processing kind {kind_number}")
            if process_kind(kind_number):
                success_count += 1

        logger.info(
            f"Successfully processed {success_count} out of {len(kind_numbers)} kinds"
        )


if __name__ == "__main__":
    main()
