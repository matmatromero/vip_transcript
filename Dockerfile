# Use the lightweight Python 3.12 image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Prevent python from buffering stdout and pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (required for some math/C++ libraries if needed)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install python dependencies natively
RUN pip install --no-cache-dir -r requirements.txt

# Create the folder structure required by the app
RUN mkdir -p raw_transcripts output/chunks

# Copy the core extraction code into the image
COPY chunker /app/chunker
COPY run_chunker.py /app/run_chunker.py
COPY ingest_db.py /app/ingest_db.py
COPY schema.sql /app/schema.sql
COPY server.py /app/server.py

# Cloud Run requires a web server listening on PORT (default 8080)
# We use Gunicorn to run the Flask app bridging Eventarc to our python logic.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 server:app
