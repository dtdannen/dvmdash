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
RUN mkdir -p /app/backend/event_collector/src
RUN mkdir -p /app/backend/shared

# Copy the application code, maintaining directory structure
COPY ./src /app/backend/event_collector/src
COPY ./shared /app/backend/shared

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV LOAD_HISTORICAL_DATA="true"
ENV HISTORICAL_DATA_BATCH_SIZE="10000"
ENV HISTORICAL_DATA_BATCH_DELAY="0.001"
ENV RELAYS="wss://relay.damus.io,wss://relay.primal.net,wss://relay.dvmdash.live,wss://relay.f7z.xyz,wss://relayable.org"
ENV START_LISTENING=true
ENV LOG_LEVEL=DEBUG
ENV DAYS_LOOKBACK=7
ENV NOSTR_LOG_LEVEL=INFO

CMD ["python", "-u", "backend/event_collector/src/main.py"]