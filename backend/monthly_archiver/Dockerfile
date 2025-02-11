FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY ./backend/monthly_archiver/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend directory
COPY ./backend/monthly_archiver /app/backend/monthly_archiver
COPY ./backend/shared /app/backend/shared

# Create logs directory
RUN mkdir -p /app/logs

CMD ["python", "-u", "backend/monthly_archiver/src/main.py"]