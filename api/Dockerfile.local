# api/Dockerfile
FROM python:3.12-slim

WORKDIR /app/api/src

COPY ./api/requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY ./api /app/api

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
