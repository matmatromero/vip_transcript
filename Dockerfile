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

# When deployed to Cloud Run or generic Docker, running ingest_db acts as an end-to-end execution wrapper
# Typically, Cloud Run expects an exposed HTTP port, but for Eventarc Triggered Jobs, a command exit works perfectly.
CMD ["python", "run_chunker.py", "--input", "raw_transcripts/", "--output", "output/chunks/"]
