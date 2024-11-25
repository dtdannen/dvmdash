# backend/celery_worker/src/tasks.py
from celery import Celery
from celery.signals import before_task_publish
import os
from deduplicator import BoundedEventDeduplicator
import sys
from loguru import logger

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Simple logging setup that works well with Docker
logger.remove()  # Remove default handler
logger.add(sys.stdout, colorize=True, level=LOG_LEVEL)


# Initialize deduplicator
deduplicator = BoundedEventDeduplicator(
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)

app = Celery("dvmdash")

# Configure Celery
app.conf.update(
    # Broker settings
    broker_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    result_backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
    # Connection settings
    broker_connection_retry_on_startup=True,
    # Task routing
    task_default_queue="dvmdash",
    task_routes={
        "process_nostr_event": {"queue": "dvmdash"},  # Explicitly route this task
        "celery_worker.src.tasks.process_nostr_event": {
            "queue": "dvmdash"
        },  # Full path version
    },
)


@before_task_publish.connect
def check_duplicate(sender=None, headers=None, body=None, **kwargs):
    """Prevent duplicate events from entering queue"""
    try:
        event_data = body[0][0]
        event_id = event_data.get("id")
        timestamp = event_data.get("created_at")

        if not event_id:
            return True

        return not deduplicator.check_duplicate(event_id, timestamp)

    except Exception as e:
        logger.error(f"Error in deduplication: {e}")
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
