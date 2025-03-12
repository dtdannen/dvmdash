FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY coordinator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code
COPY coordinator/src /app/backend/coordinator/src

# Create logs directory
RUN mkdir -p /app/logs

CMD ["python", "-u", "backend/coordinator/src/main.py"]