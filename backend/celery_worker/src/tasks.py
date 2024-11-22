# backend/celery_worker/src/tasks.py
from celery import Celery
import os

# Initialize Celery app
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
)


@app.task(bind=True, max_retries=3)
def process_nostr_event(self, event_data):
    """
    Process a Nostr event from the queue
    """
    try:
        # Process the event
        # Add any validation, transformation, or processing logic here
        # This should be pure data processing without database access
        return event_data

    except Exception as exc:
        self.retry(exc=exc, countdown=60)  # Retry in 60 seconds
