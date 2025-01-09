FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY ./backend/batch_processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend directory
COPY ./backend/batch_processor /app/backend/batch_processor
COPY ./backend/shared /app/backend/shared

# Create logs directory
RUN mkdir -p /app/logs

CMD ["python", "-u", "backend/batch_processor/src/main.py"]