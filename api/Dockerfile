# api/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY ./api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./api /app/api

CMD ["uvicorn", "api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]