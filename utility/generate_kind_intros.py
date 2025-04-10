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


def create_improved_adoc(kind_number, original_adoc, intro_sentences):
    """
    Create a new adoc file with the improved intro.

    Args:
        kind_number: The kind number
        original_adoc: Content of the original adoc file
        intro_sentences: List of 3 intro sentences

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
            original_intro
        )
        
        new_intro += modified_intro + "\n\n"

        # Replace the original intro with our new intro
        new_adoc = original_adoc.replace(intro_match.group(0), new_intro.strip())
        
        # Update the title format
        title_match = re.search(r"^= Nostr DVM Kind (\d+)( and (\d+))? Analysis", new_adoc)
        if title_match:
            if title_match.group(3):  # If there's a second kind number
                new_title = f"= Nostr DVM Kind {title_match.group(1)}/{title_match.group(3)}"
            else:
                # Check if it's a 5xxx or 6xxx kind
                kind_prefix = int(title_match.group(1)) // 1000
                new_title = f"= Nostr DVM Kind {kind_prefix}xxx"
            
            new_adoc = re.sub(r"^= Nostr DVM Kind (\d+)( and (\d+))? Analysis", new_title, new_adoc)

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


def main():
    """Main function to generate improved intros for DVM kind wiki pages."""
    parser = argparse.ArgumentParser(
        description="Generate improved introductions for DVM kind wiki pages."
    )
    parser.add_argument(
        "kind", type=int, help="The kind number to process (e.g., 5000)"
    )
    args = parser.parse_args()

    kind_number = args.kind

    # Ensure target directory exists
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # Read the existing adoc file
    adoc_success, adoc_content = read_existing_adoc(kind_number)
    if not adoc_success:
        logger.error(f"Failed to read existing adoc file: {adoc_content}")
        sys.exit(1)

    # Fetch the kind webpage if it exists
    web_success, webpage_content = fetch_kind_webpage(kind_number)
    if not web_success:
        logger.warning(
            f"Could not fetch webpage for kind {kind_number}: {webpage_content}"
        )
        webpage_content = None  # We'll proceed without the webpage content

    # Generate the intro sentences using Claude
    intro_success, intro_sentences = generate_intro_with_claude(
        kind_number, webpage_content, adoc_content
    )
    if not intro_success:
        logger.error(f"Failed to generate intro sentences: {intro_sentences}")
        sys.exit(1)

    # Create the improved adoc file
    create_success, create_message = create_improved_adoc(
        kind_number, adoc_content, intro_sentences
    )
    if not create_success:
        logger.error(f"Failed to create improved adoc file: {create_message}")
        sys.exit(1)

    logger.info(f"Successfully generated improved intro for kind {kind_number}")
    logger.info(f"New sentences:")
    for i, sentence in enumerate(intro_sentences, 1):
        logger.info(f"  {i}. {sentence}")

    logger.info(f"Output file: {TARGET_DIR / f'kind_{kind_number}_analysis.adoc'}")


if __name__ == "__main__":
    main()
