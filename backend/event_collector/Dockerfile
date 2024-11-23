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

# Copy the application code
COPY ./backend/event_collector/src ./src
COPY ./backend/shared ./shared

# Create logs directory
RUN mkdir -p /app/logs

ENV PYTHONPATH=/app

CMD ["python", "-m", "src.main"]