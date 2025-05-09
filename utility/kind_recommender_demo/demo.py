from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import torch
from transformers import AutoTokenizer, AutoModel

# from ctransformers import AutoModelForCausalLM
from llama_cpp import Llama
from huggingface_hub import hf_hub_download
import os
import psycopg2
import logging
from collections import OrderedDict
from datetime import datetime
from dotenv import load_dotenv
import sys
import anthropic
from openai import OpenAI


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("kind_recommender_demo")

# Load environment variables
load_dotenv()

# Database connection parameters
DB_HOST = os.getenv("PROD_POSTGRES_HOST")
DB_PORT = os.getenv("PROD_POSTGRES_PORT")
DB_NAME = os.getenv("PROD_POSTGRES_DB")
DB_USER = os.getenv("PROD_POSTGRES_USER")
DB_PASSWORD = os.getenv("PROD_POSTGRES_PASS")

model = SentenceTransformer("BAAI/bge-large-zh-v1.5")
kind_descriptions = {
    5000: 'Kind 5000 is a job request to extract text from an input source. The input is typically specified using an "i" tag, which may include a URL or other identifier, and can optionally include parameters like a time range to focus on or the desired text alignment. The output is the extracted text, returned in a specified format such as plain text, markdown, or VTT (Video Text Tracks).',
    5001: "Kind 5001 represents a request to summarize one or more text inputs into a condensed output. The input is provided as one or more tags, each pointing to a Nostr event containing the text to be summarized or the output of a previous DVM job. The output is the summarized text, typically in plain text or Markdown format, with an optional length parameter specifying the desired number of words or paragraphs.",
    5002: "Kind 5002 represents a request to translate text input(s) to a specified language. The input is provided as one or more tags in the event, pointing to the text to be translated. The output is the translated text, typically returned as plain text in the specified target language.",
    5050: 'Kind 5050 is a job request to generate text using AI models. The input typically includes a seed sentence or prompt in the "i" tag field for the AI to continue generating from. The output is the generated text, which can be in formats such as plain text or Markdown.',
    5100: 'Kind 5100 is a job request to generate images using AI models. The input includes a prompt provided in the "i" tag field, and optionally a second "i" tag containing a URL to an existing image for alteration. The output is a link to the generated image(s).',
    5101: "Kind 5101 appears to be a request for an AI-generated image based on an input image. The input looks like an image URL, along with some additional parameters like desired output format, bid amount, and topic tags. The output looks like a URL pointing to the generated PNG image, returned in the response event of kind 6101.",
    5102: 'DVM kind 5102 represents a request to generate an image by compositing multiple images together. The input consists of two image IDs (specified with "i" tags), a position parameter indicating where to place the images, and other metadata like bid amount and desired output format. The output, as seen in the corresponding kind 6102 responses, is a URL pointing to the generated composite image in the requested format (e.g. PNG).',
    5107: 'Kind 5107 events represent Data Vending Machine (DVM) requests on the Nostr network. The input for a kind 5107 event is typically a JSON object containing a "method" field specifying the requested data and "params" providing any necessary parameters. The output format for a kind 5107 event is specified in the "output" tag, with common formats being "text/plain" for plain text responses or other MIME types for structured data.',
    5200: "Kind 5200 is a job request to convert a video to another format. The input is a link to a video file or a social media share link. The output is the converted video file, with an optional specified output format.",
    5202: "Kind 5202 is a Data Vending Machine (DVM) job type that converts a static image into a short animated video clip. The input for this kind is a link pointing to an image file. The output is a link to the generated video.",
    5300: 'Kind 5300 is a job request to discover nostr-native content that a user might be interested in. The input is optional and can be provided by the client, but the DVM decides how to interpret it. The output is a JSON-stringified list of tags, which should be "a" (author) or "e" (event) tags pointing to recommended content.',
    5301: 'Kind 5301 is a job request to discover Nostr pubkeys that a user might be interested in following. The input is optional and can include a pubkey and additional information to guide the discovery process, which the DVM interprets based on its algorithm. The output is a JSON-stringified list of tags, typically "p" (pubkey) or "e" (event ID), representing Nostr-native content or users that may interest the requesting user.',
    5302: "Kind 5302 is a Nostr Data Vending Machine (DVM) request to search for notes based on a provided prompt. The input for a kind 5302 request includes the search text, and optionally parameters to filter the search by users, date range, and maximum number of results. The output of a kind 5302 request is a JSON-stringified list of note IDs (e tags) or pubkey IDs (p tags) that match the search criteria.",
    5303: 'Kind 5303 is a Nostr DVM request to search for user profiles based on a text prompt. The input consists of the search text and an optional max_results parameter to limit the number of returned events. The output is a JSON-stringified list of "p" tags representing the public keys of profiles matching the search criteria.',
    5304: "Kind 5304 represents a request to find and retrieve visual content related to a specific Nostr user. The input includes the user's public key, along with additional parameters like the maximum number of results to return and relays to search. The output, represented by kind 6304, contains the requested visual content that matches the specified user and parameters.",
    5312: "Kind 5312 is a request to retrieve a list of Nostr pubkeys related to a given target pubkey. The request includes parameters specifying the target pubkey and a limit on the number of results to return. The response, kind 6312, contains an array of pubkey objects along with their global pagerank scores, follower counts, and other metadata.",
    5313: "DVM kind 5313 represents a request to retrieve a personalized ranking of Nostr pubkeys. The request specifies parameters like the source pubkey to use for generating the personalized ranking, the number of results to return, and the specific ranking algorithm to use. The response, represented by kind 6313, contains a list of pubkeys along with their personalized ranking scores.",
    5314: 'Kind 5314 is a request to retrieve a list of public keys ranked by a metric called "globalPagerank". The input consists of a list of public key "targets" to rank, provided as tag parameters. The output is a JSON array containing the requested public keys along with their corresponding "globalPagerank" scores.',
    5315: "Kind 5315 is a request to search for Nostr profiles matching a given search query. The input includes parameters like the search query string and a limit on the number of results to return. The output is a list of Nostr pubkeys matching the search query, ranked by a score like a PageRank.",
    5400: "Kind 5400 represents a request to count Nostr events that match specified criteria. The input consists of zero or more tag values, each provided as a separate input. The output is a stringified number representing the count of matching events, returned in the content field of a kind 6400 event.",
    5500: 'Kind 5500 represents a job request to perform malware scanning on files. The input for kind 5500 requires clients to provide a URL in the "i" tag field, which must directly link to the file(s) to be scanned. The output for a kind 5500 request will either contain the string "CLEAN" if no malware was found, or will provide plaintext details on any malware that was detected in the scanned file(s).',
    5600: "DVM kind 5600 is a request to run a CI/CD workflow on a Git repository. The input includes parameters like the Git repository address, branch, commit ID, and workflow file path. The output includes status updates on the workflow execution, such as when it starts processing, any partial output, and the final result (success or failure).",
    5999: "Kind 5999 events represent requests made to a Data Vending Machine (DVM) for computational resources. The input for a kind 5999 event includes parameters such as CPU, memory, disk, SSH key, OS image, and OS version, which are specified using tagged data. The output of a kind 5999 event is typically a kind 7000 event that provides feedback on the status of the request, including whether payment is required, an expiration timestamp, and potentially an invoice for payment.",
}
embeddings = model.encode(list(kind_descriptions.values()))


def search(query, embeddings, texts, top_k=10):
    """
    Search for the most similar kind descriptions to the query.

    Args:
        query: The search query
        embeddings: Pre-computed embeddings for the descriptions
        texts: List of texts to search through
        top_k: Number of top results to return

    Returns:
        list: List of tuples (text, similarity_score)
    """
    query_vec = model.encode([query])
    similarities = cosine_similarity(query_vec, embeddings)[0]
    top_indices = np.argsort(similarities)[::-1][:top_k]
    return [(texts[i], similarities[i]) for i in top_indices]


def search_kinds(query, embeddings, kind_descriptions, top_k=10):
    """
    Search for the most similar kind descriptions to the query.

    Args:
        query: The search query
        embeddings: Pre-computed embeddings for the descriptions
        kind_descriptions: Dictionary mapping kind numbers to descriptions
        top_k: Number of top results to return

    Returns:
        list: List of tuples (kind_number, description, similarity_score)
    """
    query_vec = model.encode([query])
    similarities = cosine_similarity(query_vec, embeddings)[0]

    # Get the indices of the top k results
    top_indices = np.argsort(similarities)[::-1][:top_k]

    # Map indices back to kind numbers and descriptions
    kind_numbers = list(kind_descriptions.keys())
    results = []
    for i in top_indices:
        kind_number = kind_numbers[i]
        description = kind_descriptions[kind_number]
        score = similarities[i]
        results.append((kind_number, description, score))

    return results


results = search(
    "A DVM that takes text (or a list of text strings) as an input and outputs a list of embeddings",
    embeddings,
    list(kind_descriptions.values()),
)
for text, score in results:
    print(f"{text} (score: {score:.3f})")


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
        raise e


def get_event_counts_by_kind(cursor, min_kind=5000, max_kind=5999):
    """
    Query the database to get counts of events per kind and the last seen timestamp.
    Also computes the list of unused kinds in the specified range.

    Args:
        cursor: Database cursor
        min_kind: Minimum kind number to consider for unused kinds
        max_kind: Maximum kind number to consider for unused kinds

    Returns:
        tuple: (OrderedDict of kind -> {count, last_seen}, total_count, list of unused kinds)
    """
    try:
        # Get total event count
        cursor.execute("SELECT COUNT(*) FROM raw_events")
        total_count = cursor.fetchone()[0]

        # Get counts by kind
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

        # Compute unused kinds in the specified range
        used_kinds = set(counts.keys())
        all_possible_kinds = set(range(min_kind, max_kind + 1))
        unused_kinds = sorted(list(all_possible_kinds - used_kinds))

        logger.info(f"Found {len(counts)} distinct used kinds")
        logger.info(
            f"Found {len(unused_kinds)} unused kinds in range {min_kind}-{max_kind}"
        )

        return counts, total_count, unused_kinds
    except Exception as e:
        logger.error(f"Error querying event counts: {str(e)}")
        raise e


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


def find_closest_unused_kind(target_kind, unused_kinds):
    """
    Find the unused kind number that is closest to the target kind.

    Args:
        target_kind: The target kind number
        unused_kinds: List of unused kind numbers

    Returns:
        int: The closest unused kind number
    """
    if not unused_kinds:
        return None

    # Find the closest unused kind by absolute difference
    closest_kind = min(unused_kinds, key=lambda k: abs(k - target_kind))
    return closest_kind


def recommend_kind_for_query(query, min_kind=5000, max_kind=5999):
    """
    Recommend a kind number for a given query by finding the closest unused kind
    to the most similar existing kind.

    Args:
        query: The search query
        min_kind: Minimum kind number to consider
        max_kind: Maximum kind number to consider

    Returns:
        tuple: (recommended_kind, closest_existing_kind, closest_existing_description, similarity_score)
    """
    try:
        # Connect to the database
        conn = connect_to_database()
        cursor = conn.cursor()

        try:
            # Get counts and unused kinds
            counts, total_count, unused_kinds = get_event_counts_by_kind(
                cursor, min_kind, max_kind
            )

            # Search for the most similar kind descriptions
            search_results = search_kinds(query, embeddings, kind_descriptions, top_k=5)

            # Get the top result
            top_kind, top_description, top_score = search_results[0]
            logger.info(
                f"Top search result: Kind {top_kind} with score {top_score:.3f}"
            )

            # Find the closest unused kind
            recommended_kind = find_closest_unused_kind(top_kind, unused_kinds)
            logger.info(
                f"Recommended unused kind: {recommended_kind} (closest to {top_kind})"
            )

            return (recommended_kind, top_kind, top_description, top_score)

        finally:
            cursor.close()
            conn.close()

    except Exception as e:
        logger.error(f"Error recommending kind: {str(e)}")
        raise e


def generate_event_counts_adoc(
    include_unused_kinds=False, min_kind=5000, max_kind=5999
):
    """
    Generate an AsciiDoc string with a table of event counts by kind.

    Args:
        include_unused_kinds: Whether to include a section for unused kinds
        min_kind: Minimum kind number to consider for unused kinds
        max_kind: Maximum kind number to consider for unused kinds

    Returns:
        str: AsciiDoc formatted string with event counts by kind
    """
    try:
        # Connect to the database
        conn = connect_to_database()
        cursor = conn.cursor()

        try:
            # Get counts and last seen timestamps by kind
            counts, total_count, unused_kinds = get_event_counts_by_kind(
                cursor, min_kind, max_kind
            )
            logger.info(f"Found {len(counts)} distinct event kinds")

            # Generate AsciiDoc content
            adoc_content = ""

            # Document header
            adoc_content += "= Nostr Event Counts by Kind\n"
            adoc_content += ":toc:\n"
            adoc_content += ":toclevels: 2\n"
            adoc_content += ":source-highlighter: highlight.js\n\n"

            # Introduction
            adoc_content += "== Introduction\n\n"
            adoc_content += "This document provides a count of Nostr events by kind in the raw_events database table.\n\n"
            adoc_content += f"Total events in database: {total_count:,}\n\n"
            adoc_content += (
                f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )

            # Event counts table
            adoc_content += "== Event Counts by Kind\n\n"
            adoc_content += '[options="header"]\n'
            adoc_content += "|===\n"
            adoc_content += "|Kind|Count|Percentage of Total|Last Seen|Description\n"

            # Add rows for each kind
            for kind, data in counts.items():
                count = data["count"]
                last_seen = data["last_seen"]
                percentage = (count / total_count) * 100 if total_count > 0 else 0

                # Calculate time since last seen
                time_since = calculate_time_since(last_seen)

                # Get description if available
                description = kind_descriptions.get(kind, "")
                description_snippet = (
                    description[:50] + "..."
                    if description and len(description) > 50
                    else description
                )

                adoc_content += f"|{kind}|{count:,}|{percentage:.2f}%|{time_since}|{description_snippet}\n"

            adoc_content += "|===\n\n"

            # Add unused kinds section if requested
            if include_unused_kinds and unused_kinds:
                adoc_content += "== Unused Kinds\n\n"
                adoc_content += (
                    "These kind numbers have never been used in the database:\n\n"
                )
                adoc_content += '[options="header"]\n'
                adoc_content += "|===\n"
                adoc_content += "|Kind|Description\n"

                for kind in unused_kinds:
                    # Get description if available
                    description = kind_descriptions.get(kind, "")
                    adoc_content += f"|{kind}|{description}\n"

                adoc_content += "|===\n\n"

            return adoc_content

        finally:
            cursor.close()
            conn.close()

    except Exception as e:
        logger.error(f"Error generating event counts AsciiDoc: {str(e)}")
        return f"Error generating event counts: {str(e)}"


# Example usage for generating AsciiDoc:
# adoc_content = generate_event_counts_adoc(include_unused_kinds=True)
# print(adoc_content)
#
# # To save to a file:
# with open("event_counts_by_kind.adoc", "w") as f:
#     f.write(adoc_content)


# Download MobileLLaMA model if it doesn't exist
model_path = "MobileLLaMA-1.4B-Base-Q4_K_M.gguf"
if not os.path.exists(model_path):
    logger.info(f"Downloading MobileLLaMA model to {model_path}")
    hf_hub_download(
        repo_id="tensorblock/MobileLLaMA-1.4B-Base-GGUF",
        filename="MobileLLaMA-1.4B-Base-Q4_K_M.gguf",
        local_dir=".",
    )

# Initialize MobileLLaMA model
logger.info("Initializing MobileLLaMA model")
llm = Llama(
    model_path=model_path,
    n_ctx=512,  # Context window size
    n_threads=4,  # CPU threads
    n_gpu_layers=0,  # Set to 0 for CPU-only
)


def generate_kind_summary_tinyllama(
    query, recommended_kind, similar_kind, similar_description, score
):
    """
    Generate a summary using MobileLLaMA to explain which kind the user should consider using and why.
    (Function name kept as tinyllama for backward compatibility)

    Args:
        query: The original query
        recommended_kind: The recommended unused kind number
        similar_kind: The most similar existing kind number
        similar_description: Description of the most similar kind
        score: Similarity score

    Returns:
        str: LLM-generated summary explaining the recommendation
    """
    # Create a prompt for MobileLLaMA with a more direct instruction to avoid repetition
    prompt = f"""You are a helpful assistant specializing in Nostr Data Vending Machines (DVMs).

For a DVM that would "{query}", the recommended kind number is {recommended_kind}.

This is similar to existing kind {similar_kind}: "{similar_description}"

Write a concise explanation (2-3 sentences) of why kind {recommended_kind} is appropriate for this DVM task and how it relates to kind {similar_kind}. Do not repeat the prompt or instructions in your response.

"""

    # Print the prompt for debugging
    print("\n=== MobileLLaMA Prompt ===")
    print(prompt)
    print("==========================\n")

    # Generate summary using MobileLLaMA
    output = llm(
        prompt, max_tokens=200, temperature=0.7, top_p=0.9, top_k=40, repeat_penalty=1.2
    )

    # Extract the generated text from the response
    summary = output["choices"][0]["text"]

    return summary


def generate_kind_summary_claude(
    query, recommended_kind, similar_kind, similar_description, score
):
    """
    Generate a summary using Claude Haiku to explain which kind the user should consider using and why.

    Args:
        query: The original query
        recommended_kind: The recommended unused kind number
        similar_kind: The most similar existing kind number
        similar_description: Description of the most similar kind
        score: Similarity score

    Returns:
        str: LLM-generated summary explaining the recommendation
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return "Error: ANTHROPIC_API_KEY environment variable not set"

    # Create the client
    client = anthropic.Anthropic(api_key=api_key)

    # Prepare the prompt
    prompt = f"""
For a DVM (Data Vending Machine) that would "{query}", the recommended kind number is {recommended_kind}.

This is similar to existing kind {similar_kind}: "{similar_description}"

Explain why kind {recommended_kind} is appropriate for this DVM task and how it relates to kind {similar_kind}.
"""

    # Print the prompt for debugging
    print("\n=== Claude Haiku Prompt ===")
    print(prompt)
    print("==========================\n")

    # Also print the system prompt
    system_prompt = "You are a helpful assistant specializing in Nostr Data Vending Machines (DVMs)."
    print("=== Claude System Prompt ===")
    print(system_prompt)
    print("===========================\n")

    try:
        # Make the API call
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            temperature=0.7,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the summary from the response
        summary = response.content[0].text
        return summary

    except Exception as e:
        logger.error(f"Error calling Claude API: {str(e)}")
        return f"Error calling Claude API: {str(e)}"


def generate_kind_summary_lmstudio(
    query, recommended_kind, similar_kind, similar_description, score
):
    """
    Generate a summary using a local LM Studio model to explain which kind the user should consider using and why.

    Args:
        query: The original query
        recommended_kind: The recommended unused kind number
        similar_kind: The most similar existing kind number
        similar_description: Description of the most similar kind
        score: Similarity score

    Returns:
        str: LLM-generated summary explaining the recommendation
    """
    try:
        # Point to the local LM Studio server
        client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

        # Prepare the system prompt
        system_prompt = "You are a helpful assistant specializing in Nostr Data Vending Machines (DVMs)."

        # Prepare the user prompt
        user_prompt = f"""
For a DVM (Data Vending Machine) that would "{query}", the recommended kind number is {recommended_kind}.

This is similar to existing kind {similar_kind}: "{similar_description}"

Explain why kind {recommended_kind} is appropriate for this DVM task and how it relates to kind {similar_kind}.
"""

        # Print the prompts for debugging
        print("\n=== LM Studio Prompt ===")
        print(user_prompt)
        print("=======================\n")

        print("=== LM Studio System Prompt ===")
        print(system_prompt)
        print("==============================\n")

        # Make the API call
        completion = client.chat.completions.create(
            model="model-identifier",  # This is ignored by LM Studio but required by the API
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )

        # Extract the summary from the response
        summary = completion.choices[0].message.content
        return summary

    except Exception as e:
        logger.error(f"Error calling LM Studio API: {str(e)}")
        return f"Error calling LM Studio API: {str(e)}"


def generate_kind_decision_claude(query, similar_kinds):
    """
    Generate a decision using Claude Haiku on whether to reuse an existing kind or create a new one.

    Args:
        query: The search query describing the new DVM
        similar_kinds: List of tuples (kind_number, description, similarity_score)

    Returns:
        tuple: (reuse_existing, kind_to_use, reasoning)
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return False, 0, "Error: ANTHROPIC_API_KEY environment variable not set"

    # Format the similar kinds for the prompt
    similar_kinds_text = ""
    for i, (kind, description, score) in enumerate(similar_kinds[:3]):
        similar_kinds_text += (
            f"Kind {kind} (similarity: {score:.2f}): {description}\n\n"
        )

    # System prompt
    system_prompt = "You are an expert on Nostr Data Vending Machines (DVMs) and their kind numbers."

    # User prompt
    user_prompt = f"""A developer wants to create a new DVM with this description:
"{query}"

Here are the most similar existing DVM kinds:
{similar_kinds_text}

GUIDELINES FOR REUSING VS. CREATING NEW KINDS:

STRICT CRITERIA:
- CREATE A NEW KIND if the input representation OR output representation differs from existing kinds
- REUSE AN EXISTING KIND if BOTH the input representation AND output representation match an existing kind

Additional considerations:
- Input representation refers to the format, structure, and type of data the DVM accepts
- Output representation refers to the format, structure, and type of data the DVM produces
- Different output data types ALWAYS require a new kind (e.g., text vs. embeddings vs. images vs. JSON)
- Different output formats ALWAYS require a new kind (e.g., plain text vs. vector/matrix vs. URL)
- Functional similarity is NOT sufficient for reuse if the output representation differs
- Minor variations in parameters or optional fields are acceptable for reuse
- Fundamental changes to data structure or format require a new kind

Examples of different output representations requiring new kinds:
- Text summaries vs. vector embeddings (even though both process text, they produce different outputs)
- Images vs. URLs to images (different data types)
- Plain text vs. JSON (different formats)

Based on these guidelines, analyze whether the developer should:
1. Reuse one of the existing kinds above, OR
2. Create a new kind number

First, analyze the input types, output types, and core functionality of both the proposed DVM and the existing kinds.
Then make a clear recommendation with detailed reasoning.

Your response must be in this exact format:
DECISION: [REUSE or NEW]
KIND: [kind number to use - either existing or recommended new one]
REASONING: [detailed explanation of your decision, analyzing input/output similarities and differences]
"""

    # Print the prompts for debugging
    print("\n=== Claude Decision Prompt ===")
    print(user_prompt)
    print("=============================\n")

    try:
        # Create the client
        client = anthropic.Anthropic(api_key=api_key)

        # Make the API call
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            temperature=0.2,  # Lower temperature for more consistent reasoning
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract the response
        result = response.content[0].text.strip()

        # Print the raw response for debugging
        print("\n=== Claude Raw Response ===")
        print(result)
        print("==========================\n")

        # Parse the response
        lines = result.split("\n")
        decision_line = next(
            (line for line in lines if line.startswith("DECISION:")), ""
        )
        kind_line = next((line for line in lines if line.startswith("KIND:")), "")

        if not decision_line or not kind_line:
            logger.error(f"Failed to parse Claude response: {result}")
            return False, 0, "Error: Failed to parse Claude response"

        decision = decision_line.replace("DECISION:", "").strip()
        try:
            kind = int(kind_line.replace("KIND:", "").strip())
        except ValueError:
            logger.error(f"Failed to parse kind number from: {kind_line}")
            kind = 0

        # Extract reasoning (everything after KIND: line)
        reasoning_start = lines.index(kind_line) + 1
        reasoning = "\n".join(lines[reasoning_start:]).strip()
        if reasoning.startswith("REASONING:"):
            reasoning = reasoning.replace("REASONING:", "", 1).strip()

        return (decision.upper() == "REUSE"), kind, reasoning

    except Exception as e:
        logger.error(f"Error calling Claude API: {str(e)}")
        return False, 0, f"Error calling Claude API: {str(e)}"


def generate_kind_decision_lmstudio(query, similar_kinds):
    """
    Generate a decision using LM Studio on whether to reuse an existing kind or create a new one.

    Args:
        query: The search query describing the new DVM
        similar_kinds: List of tuples (kind_number, description, similarity_score)

    Returns:
        tuple: (reuse_existing, kind_to_use, reasoning)
    """
    try:
        # Point to the local LM Studio server
        client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

        # Format the similar kinds for the prompt
        similar_kinds_text = ""
        for i, (kind, description, score) in enumerate(similar_kinds[:3]):
            similar_kinds_text += (
                f"Kind {kind} (similarity: {score:.2f}): {description}\n\n"
            )

        # System prompt
        system_prompt = "You are an expert on Nostr Data Vending Machines (DVMs) and their kind numbers."

        # User prompt - same as Claude for consistency
        user_prompt = f"""A developer wants to create a new DVM with this description:
"{query}"

Here are the most similar existing DVM kinds:
{similar_kinds_text}

GUIDELINES FOR REUSING VS. CREATING NEW KINDS:

STRICT CRITERIA:
- CREATE A NEW KIND if the input representation OR output representation differs from existing kinds
- REUSE AN EXISTING KIND if BOTH the input representation AND output representation match an existing kind

Additional considerations:
- Input representation refers to the format, structure, and type of data the DVM accepts
- Output representation refers to the format, structure, and type of data the DVM produces
- Different output data types ALWAYS require a new kind (e.g., text vs. embeddings vs. images vs. JSON)
- Different output formats ALWAYS require a new kind (e.g., plain text vs. vector/matrix vs. URL)
- Functional similarity is NOT sufficient for reuse if the output representation differs
- Minor variations in parameters or optional fields are acceptable for reuse
- Fundamental changes to data structure or format require a new kind

Examples of different output representations requiring new kinds:
- Text summaries vs. vector embeddings (even though both process text, they produce different outputs)
- Images vs. URLs to images (different data types)
- Plain text vs. JSON (different formats)

Based on these guidelines, analyze whether the developer should:
1. Reuse one of the existing kinds above, OR
2. Create a new kind number

First, analyze the input types, output types, and core functionality of both the proposed DVM and the existing kinds.
Then make a clear recommendation with detailed reasoning.

Your response must be in this exact format:
DECISION: [REUSE or NEW]
KIND: [kind number to use - either existing or recommended new one]
REASONING: [detailed explanation of your decision, analyzing input/output similarities and differences]
"""

        # Print the prompts for debugging
        print("\n=== LM Studio Decision Prompt ===")
        print(user_prompt)
        print("================================\n")

        # Make the API call
        completion = client.chat.completions.create(
            model="model-identifier",  # This is ignored by LM Studio but required by the API
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,  # Lower temperature for more consistent reasoning
            max_tokens=1000,
        )

        # Extract the response
        result = completion.choices[0].message.content.strip()

        # Print the raw response for debugging
        print("\n=== LM Studio Raw Response ===")
        print(result)
        print("==============================\n")

        # Parse the response
        lines = result.split("\n")
        decision_line = next(
            (line for line in lines if line.startswith("DECISION:")), ""
        )
        kind_line = next((line for line in lines if line.startswith("KIND:")), "")

        if not decision_line or not kind_line:
            logger.error(f"Failed to parse LM Studio response: {result}")
            return False, 0, "Error: Failed to parse LM Studio response"

        decision = decision_line.replace("DECISION:", "").strip()
        try:
            kind = int(kind_line.replace("KIND:", "").strip())
        except ValueError:
            logger.error(f"Failed to parse kind number from: {kind_line}")
            kind = 0

        # Extract reasoning (everything after KIND: line)
        reasoning_start = lines.index(kind_line) + 1
        reasoning = "\n".join(lines[reasoning_start:]).strip()
        if reasoning.startswith("REASONING:"):
            reasoning = reasoning.replace("REASONING:", "", 1).strip()

        return (decision.upper() == "REUSE"), kind, reasoning

    except Exception as e:
        logger.error(f"Error calling LM Studio API: {str(e)}")
        return False, 0, f"Error calling LM Studio API: {str(e)}"


def generate_kind_explanation_claude(
    query, reuse_existing, kind_to_use, reasoning, similar_kinds
):
    """
    Generate a user-friendly explanation using Claude Haiku.

    Args:
        query: The search query describing the new DVM
        reuse_existing: Boolean indicating whether to reuse an existing kind
        kind_to_use: The kind number to use (either existing or new)
        reasoning: The reasoning behind the decision
        similar_kinds: List of tuples (kind_number, description, similarity_score)

    Returns:
        str: User-friendly explanation
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return "Error: ANTHROPIC_API_KEY environment variable not set"

    # Get the most similar kind for reference
    most_similar_kind, most_similar_desc, _ = similar_kinds[0]

    # System prompt
    system_prompt = "You are a helpful assistant specializing in Nostr Data Vending Machines (DVMs)."

    # User prompt based on decision
    if reuse_existing:
        # Find the description of the kind to reuse
        kind_desc = next(
            (desc for k, desc, _ in similar_kinds if k == kind_to_use),
            "Description not available",
        )

        user_prompt = f"""A developer wants to create a DVM that would: "{query}"

You've analyzed this request and determined they should REUSE existing kind {kind_to_use}.
Kind {kind_to_use} description: "{kind_desc}"

Expert reasoning: {reasoning}

Write a helpful, conversational explanation (3-5 sentences) that:
1. Clearly recommends using the existing kind {kind_to_use}
2. Explains why reusing this kind is appropriate, focusing on input/output similarities
3. Mentions any adaptations they might need to make
4. Emphasizes the benefits of kind reuse (ecosystem standardization, client compatibility)

Your explanation should be informative but friendly, and should help the developer understand why reusing an existing kind is the right choice in this case.
"""
    else:
        user_prompt = f"""A developer wants to create a DVM that would: "{query}"

You've analyzed this request and determined they should create a NEW kind {kind_to_use}.
Most similar existing kind for reference - Kind {most_similar_kind}: "{most_similar_desc}"

Expert reasoning: {reasoning}

Write a helpful, conversational explanation (3-5 sentences) that:
1. Clearly recommends creating a new kind {kind_to_use}
2. Explains why a new kind is needed, focusing on input/output differences
3. Describes how this new kind relates to but differs from kind {most_similar_kind}
4. Suggests how they should document the new kind's input/output format

Your explanation should be informative but friendly, and should help the developer understand why creating a new kind is the right choice in this case.
"""

    # Print the prompts for debugging
    print("\n=== Claude Explanation Prompt ===")
    print(user_prompt)
    print("===============================\n")

    try:
        # Create the client
        client = anthropic.Anthropic(api_key=api_key)

        # Make the API call
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=800,
            temperature=0.7,  # Higher temperature for more creative explanations
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract the explanation
        explanation = response.content[0].text.strip()
        return explanation

    except Exception as e:
        logger.error(f"Error calling Claude API: {str(e)}")
        return f"Error calling Claude API: {str(e)}"


def generate_kind_explanation_lmstudio(
    query, reuse_existing, kind_to_use, reasoning, similar_kinds
):
    """
    Generate a user-friendly explanation using LM Studio.

    Args:
        query: The search query describing the new DVM
        reuse_existing: Boolean indicating whether to reuse an existing kind
        kind_to_use: The kind number to use (either existing or new)
        reasoning: The reasoning behind the decision
        similar_kinds: List of tuples (kind_number, description, similarity_score)

    Returns:
        str: User-friendly explanation
    """
    try:
        # Point to the local LM Studio server
        client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

        # Get the most similar kind for reference
        most_similar_kind, most_similar_desc, _ = similar_kinds[0]

        # System prompt
        system_prompt = "You are a helpful assistant specializing in Nostr Data Vending Machines (DVMs)."

        # User prompt based on decision - same as Claude for consistency
        if reuse_existing:
            # Find the description of the kind to reuse
            kind_desc = next(
                (desc for k, desc, _ in similar_kinds if k == kind_to_use),
                "Description not available",
            )

            user_prompt = f"""A developer wants to create a DVM that would: "{query}"

You've analyzed this request and determined they should REUSE existing kind {kind_to_use}.
Kind {kind_to_use} description: "{kind_desc}"

Expert reasoning: {reasoning}

Write a helpful, conversational explanation (3-5 sentences) that:
1. Clearly recommends using the existing kind {kind_to_use}
2. Explains why reusing this kind is appropriate, focusing on input/output similarities
3. Mentions any adaptations they might need to make
4. Emphasizes the benefits of kind reuse (ecosystem standardization, client compatibility)

Your explanation should be informative but friendly, and should help the developer understand why reusing an existing kind is the right choice in this case.
"""
        else:
            user_prompt = f"""A developer wants to create a DVM that would: "{query}"

You've analyzed this request and determined they should create a NEW kind {kind_to_use}.
Most similar existing kind for reference - Kind {most_similar_kind}: "{most_similar_desc}"

Expert reasoning: {reasoning}

Write a helpful, conversational explanation (3-5 sentences) that:
1. Clearly recommends creating a new kind {kind_to_use}
2. Explains why a new kind is needed, focusing on input/output differences
3. Describes how this new kind relates to but differs from kind {most_similar_kind}
4. Suggests how they should document the new kind's input/output format

Your explanation should be informative but friendly, and should help the developer understand why creating a new kind is the right choice in this case.
"""

        # Print the prompts for debugging
        print("\n=== LM Studio Explanation Prompt ===")
        print(user_prompt)
        print("==================================\n")

        # Make the API call
        completion = client.chat.completions.create(
            model="model-identifier",  # This is ignored by LM Studio but required by the API
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,  # Higher temperature for more creative explanations
            max_tokens=800,
        )

        # Extract the explanation
        explanation = completion.choices[0].message.content.strip()
        return explanation

    except Exception as e:
        logger.error(f"Error calling LM Studio API: {str(e)}")
        return f"Error calling LM Studio API: {str(e)}"


# For backward compatibility
def generate_kind_summary(
    query, recommended_kind, similar_kind, similar_description, score
):
    """
    Generate a summary using MobileLLaMA to explain which kind the user should consider using and why.
    This is a wrapper for backward compatibility.
    """
    return generate_kind_summary_tinyllama(
        query, recommended_kind, similar_kind, similar_description, score
    )


def example_kind_recommendation(query):
    """
    Example function demonstrating how to recommend a kind number for a new DVM type.

    Args:
        query: Description of the new DVM type

    Returns:
        str: Recommendation result as a formatted string
    """
    # Search for similar kinds
    search_results = search_kinds(query, embeddings, kind_descriptions, top_k=3)

    # Print search results
    print(f"Top 3 similar kinds for query: '{query}'")
    for kind, description, score in search_results:
        print(f"Kind {kind}: {score:.3f} - {description[:100]}...")

    # Get recommendation
    recommended_kind, similar_kind, similar_description, score = (
        recommend_kind_for_query(query)
    )

    # Generate summaries using all three models
    mobilellama_summary = generate_kind_summary_tinyllama(
        query, recommended_kind, similar_kind, similar_description, score
    )

    claude_summary = generate_kind_summary_claude(
        query, recommended_kind, similar_kind, similar_description, score
    )

    # Try to get LM Studio summary, but handle potential errors gracefully
    try:
        lmstudio_summary = generate_kind_summary_lmstudio(
            query, recommended_kind, similar_kind, similar_description, score
        )
    except Exception as e:
        logger.error(f"Error getting LM Studio summary: {str(e)}")
        lmstudio_summary = "Error: LM Studio server not available. Make sure LM Studio is running on http://localhost:1234"

    # Format result with all three summaries for comparison
    result = f"""
Recommendation for: '{query}'

Most similar existing kind: {similar_kind} (similarity score: {score:.3f})
Description: {similar_description}...

Recommended unused kind: {recommended_kind}
(This is the closest unused kind to {similar_kind})

MobileLLaMA Summary:
{mobilellama_summary}

Claude Haiku Summary:
{claude_summary}

LM Studio Summary:
{lmstudio_summary}
"""
    return result


def improved_kind_recommendation(query):
    """
    Improved function for recommending kind numbers with better LLM-based decision making.
    Uses both Claude Haiku and LM Studio for comparison.

    Args:
        query: Description of the new DVM type

    Returns:
        str: Recommendation result as a formatted string with both models' outputs
    """
    # Search for similar kinds using embeddings (just for retrieval)
    search_results = search_kinds(query, embeddings, kind_descriptions, top_k=5)

    # Print search results
    print(f"Top 5 similar kinds for query: '{query}'")
    for kind, description, score in search_results[:5]:
        print(f"Kind {kind}: {score:.3f} - {description[:100]}...")

    # Get recommendation for a new kind if needed
    recommended_kind, _, _, _ = recommend_kind_for_query(query)

    # Use both LLMs to decide whether to reuse or create new
    print("\nGenerating decisions using Claude Haiku and LM Studio...")
    claude_reuse, claude_kind, claude_reasoning = generate_kind_decision_claude(
        query, search_results
    )
    lmstudio_reuse, lmstudio_kind, lmstudio_reasoning = generate_kind_decision_lmstudio(
        query, search_results
    )

    # If creating new, use the recommended kind from database
    if not claude_reuse:
        claude_kind = recommended_kind
    if not lmstudio_reuse:
        lmstudio_kind = recommended_kind

    # Generate user-friendly explanations from both models
    print("\nGenerating explanations using Claude Haiku and LM Studio...")
    claude_explanation = generate_kind_explanation_claude(
        query, claude_reuse, claude_kind, claude_reasoning, search_results
    )
    lmstudio_explanation = generate_kind_explanation_lmstudio(
        query, lmstudio_reuse, lmstudio_kind, lmstudio_reasoning, search_results
    )

    # Format the complete result with both models' outputs
    result = f"""
Recommendation for: '{query}'

=== CLAUDE HAIKU RECOMMENDATION ===
{'REUSE EXISTING KIND' if claude_reuse else 'CREATE NEW KIND'}: {claude_kind}

Expert Reasoning:
{claude_reasoning}

Explanation for Developer:
{claude_explanation}

=== LM STUDIO RECOMMENDATION ===
{'REUSE EXISTING KIND' if lmstudio_reuse else 'CREATE NEW KIND'}: {lmstudio_kind}

Expert Reasoning:
{lmstudio_reasoning}

Explanation for Developer:
{lmstudio_explanation}

=== TOP SIMILAR KINDS FOR REFERENCE ===
"""

    # Add the top similar kinds for reference
    for kind, description, score in search_results[:3]:
        result += f"- Kind {kind} (similarity: {score:.3f}): {description[:100]}...\n"

    return result


# Example of how to use the original kind recommendation:
# query = "A DVM that generates embeddings from text input"
# recommendation = example_kind_recommendation(query)
# print(recommendation)

# Example of how to use the improved kind recommendation
# query = "A DVM that summarizes one or more text inputs"
# query = "A DVM that handles requests for CI/CD Git pipeline workflow for a git repo"
# query = "A DVM that generates embeddings from text input"
query = "A DVM that translates text from one language to another"
recommendation = improved_kind_recommendation(query)
print(recommendation)

# Example test queries to try:
# "A DVM that generates embeddings from text input"
# "A DVM that translates text from one language to another"
# "A DVM that creates images based on text prompts and another image"
# "A DVM that counts events matching specific criteria but with additional metadata"
# "A DVM that converts video to a different format with custom filters"
