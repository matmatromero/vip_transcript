# Use the lightweight Python 3.12 image
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install cloud-only dependencies (no sentence-transformers/PyTorch needed)
COPY requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt

RUN mkdir -p raw_transcripts output/chunks

# Copy application code (this layer changes most often, so it goes last)
COPY chunker /app/chunker
COPY run_chunker.py /app/run_chunker.py
COPY ingest_db.py /app/ingest_db.py
COPY schema.sql /app/schema.sql
COPY server.py /app/server.py

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 server:app
