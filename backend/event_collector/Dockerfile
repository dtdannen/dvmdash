FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY ./backend/event_collector/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/logs
RUN mkdir -p /test_data

# Copy the application code, including shared
COPY ./backend/event_collector/src ./src
COPY ./backend/shared ./shared

# Copy the startup script
COPY ./backend/event_collector/docker_entrypoint.sh /app/
RUN chmod +x /app/docker_entrypoint.sh

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV USE_TEST_DATA="false"
ENV TEST_DATA_BATCH_SIZE="10000"
ENV TEST_DATA_BATCH_DELAY="1.0"

ENTRYPOINT ["/app/docker_entrypoint.sh"]