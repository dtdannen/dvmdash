# api/Dockerfile
FROM python:3.12-slim

WORKDIR /app/api/src

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/api

# Configure Uvicorn's log format to match our other services
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/api/logging_config.json"]
