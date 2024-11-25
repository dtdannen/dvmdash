# backend/celery_worker/src/tasks.py
from celery import Celery
from celery.signals import before_task_publish
import os
from .deduplicator import BoundedEventDeduplicator
import sys
from loguru import logger
from shared.config.celery_config import CELERY_CONFIG  # Import shared config

app = Celery("dvmdash")
app.config_from_object(CELERY_CONFIG)


# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)


# Initialize deduplicator
deduplicator = BoundedEventDeduplicator(
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)


@before_task_publish.connect
def check_duplicate(sender=None, headers=None, body=None, **kwargs):
    """Prevent duplicate events from entering queue"""
    try:
        if not body or not isinstance(body, (list, tuple)) or not body[0]:
            logger.warning("Invalid task body format")
            return True

        event_data = body[0][0]
        if not isinstance(event_data, dict):
            logger.warning("Invalid event data format")
            return True

        event_id = event_data.get("id")
        timestamp = event_data.get("created_at")

        if not event_id:
            logger.warning("Missing event ID")
            return True

        is_duplicate = deduplicator.check_duplicate(event_id, timestamp)
        if is_duplicate:
            logger.info(f"Duplicate event detected and skipped: {event_id}")

        return not is_duplicate

    except Exception as e:
        logger.error(f"Error in deduplication: {e}", exc_info=True)
        return True


@app.task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),  # Auto-retry for all exceptions
    retry_backoff=True,  # Exponential backoff
    retry_backoff_max=600,  # Max delay between retries (10 minutes)
    acks_late=True,  # Task acknowledged after completion
    queue="dvmdash",  # Also specify the queue here
)
def process_nostr_event(self, event_data):
    """
    Process a Nostr event from the queue

    Args:
        event_data (dict): The Nostr event data to process

    Returns:
        dict: The processed event data

    Raises:
        Exception: If processing fails
    """
    try:
        # Process the event
        # Add any validation, transformation, or processing logic here
        return event_data

    except Exception as exc:
        # Log the error before retrying
        self.logger.error(f"Error processing event: {exc}")
        raise exc  # This will trigger the autoretry
