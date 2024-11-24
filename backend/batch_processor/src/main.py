import os
import sys
import time
import loguru
import redis
import json
import base64
import traceback

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger = loguru.logger
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)


def extract_nostr_event(message):
    """
    Extract the Nostr event from a Celery task message in Redis.

    Args:
        message: Raw message from Redis queue

    Returns:
        dict: The Nostr event data
    """
    try:
        # Parse the outer message
        message_data = json.loads(message)

        # Get the base64 encoded body
        if isinstance(message_data, str):
            message_data = json.loads(message_data)

        body = message_data.get("body")
        if not body:
            raise ValueError("No body found in message")

        # Decode the base64 body
        decoded_body = base64.b64decode(body).decode("utf-8")

        # The body contains a list with the task args and kwargs
        body_data = json.loads(decoded_body)

        # The event data should be the first argument
        if not isinstance(body_data, list) or len(body_data) < 1:
            raise ValueError("Invalid message structure")

        event_data = body_data[0][0]  # First item of first argument array
        if not isinstance(event_data, dict):
            raise ValueError("Event data is not a dictionary")

        return event_data

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to parse message: {str(e)}")
        logger.debug(f"Raw message: {message[:200]}...")  # First 200 chars
        raise


def process_events():
    """
    Simple function to pull events from Redis and count them
    """
    event_count = 0
    error_count = 0

    # Connect to Redis
    redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
    queue_name = "dvmdash"

    logger.info(f"Starting event processing loop - watching queue: {queue_name}")

    while True:
        try:
            # Get current queue length periodically
            if event_count % 100 == 0:
                queue_length = redis_client.llen(queue_name)
                logger.info(f"Current queue length: {queue_length}")

            # Try to get a message from the queue using BRPOP
            result = redis_client.brpop(queue_name, timeout=1)

            if result:
                _, message = result
                try:
                    logger.debug(f"raw event is: {message}")
                    # Extract the Nostr event from the Celery message
                    event_data = extract_nostr_event(message)
                    event_count += 1

                    # Extract key fields, using get() for safety
                    kind = event_data.get("kind")
                    event_id = event_data.get("id")
                    pubkey = event_data.get("pubkey")
                    created_at = event_data.get("created_at")
                    tags = event_data.get("tags", [])

                    if event_id:  # Only log if we have a valid event ID
                        # Log basic event info at INFO level
                        logger.info(
                            f"Event {event_count} | "
                            f"Kind: {kind} | "
                            f"ID: {event_id[:8]}... | "  # Just show first 8 chars
                            f"Time: {created_at}"
                        )

                        # Log detailed event data at DEBUG level
                        logger.debug("Event details:")
                        logger.debug(f"Full ID: {event_id}")
                        logger.debug(f"Pubkey: {pubkey}")
                        logger.debug(f"Tags: {tags}")
                        logger.debug(
                            f"Content length: {len(event_data.get('content', ''))}"
                        )
                    else:
                        logger.warning("Received event with no ID")
                        logger.debug(f"Invalid event data: {event_data}")

                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Failed to parse message: {str(e)}")
                    logger.debug(f"Raw message: {message[:200]}...")  # First 200 chars

            else:
                logger.debug("No messages in queue, waiting...")

        except Exception as e:
            error_count += 1
            logger.error(f"Error processing message (Error count: {error_count})")
            logger.error(traceback.format_exc())

            if error_count >= 10:
                logger.critical("Too many consecutive errors, shutting down...")
                sys.exit(1)

            time.sleep(1)
        else:
            # Reset error count on successful processing
            error_count = 0


if __name__ == "__main__":
    logger.info("DVMDash batch processor starting up...")
    try:
        process_events()
    except KeyboardInterrupt:
        logger.info("Shutting down batch processor...")
    except Exception as e:
        logger.exception("Fatal error in batch processor")
        sys.exit(1)
