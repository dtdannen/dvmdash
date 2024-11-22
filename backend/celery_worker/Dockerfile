# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY ./backend/celery_worker/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy celery worker code
COPY ./backend/celery_worker/src /app/celery_worker/src

# Set up a non-root user for security
RUN useradd -m celery_user && \
    chown -R celery_user:celery_user /app
USER celery_user

# Command to run celery worker
CMD ["celery", "-A", "celery_worker.src.tasks", "worker", "--loglevel=info"]