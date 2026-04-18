import os
from flask import Flask, request, jsonify
from google.cloud import storage
import subprocess
from pathlib import Path

app = Flask(__name__)

# Ensure local directories exist for the container to do its work
os.makedirs("raw_transcripts", exist_ok=True)
os.makedirs("output/chunks", exist_ok=True)

@app.route("/", methods=["POST"])
def eventarc_receiver():
    """
    Receives HTTP POST requests from GCP Eventarc whenever a new transcript lands in GCS.
    """
    event = request.get_json()
    if not event:
        return "Bad Request: No JSON body", 400

    # Extract bucket and file details from the Eventarc payload
    bucket_name = event.get("bucket")
    file_name = event.get("name")
    
    if not bucket_name or not file_name:
        # Some Eventarc setups pass details in headers instead of JSON
        bucket_name = request.headers.get("ce-subject", "").split("objects/")[-1] or request.headers.get("ce-bucket")
        file_name = request.headers.get("ce-subject", "").split("objects/")[-1] or request.headers.get("ce-object")

    if not bucket_name or not file_name:
        return "Ignored: Could not find bucket or object name", 200
        
    print(f"Trigger received for: gs://{bucket_name}/{file_name}")

    if not file_name.endswith('.txt'):
        return "Ignored: Not a transcript .txt file.", 200

    # 1. Download the file from GCS
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    
    local_input_path = f"raw_transcripts/{os.path.basename(file_name)}"
    blob.download_to_filename(local_input_path)
    print(f"Downloaded {file_name} successfully.")

    # 2. Execute the semantic chunker pipeline via Vertex AI
    # Cloud Run populates GOOGLE_CLOUD_PROJECT automatically if we need it
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "tonal-transit-435411-i4")
    
    print("Running semantic chunker...")
    result = subprocess.run([
        "python", "run_chunker.py", 
        "--input", "raw_transcripts/",
        "--output", "output/chunks/",
        "--embedder", "vertexai",
        "--gcp-project", project_id,
        "--gcp-location", "us-central1"  # Or your chosen region
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Pipeline Error: {result.stderr}")
        return jsonify({"error": "Pipeline failed", "details": result.stderr}), 500
        
    # 3. Ingest into the PostgreSQL Database securely
    print("Ingesting into RAG Database...")
    db_result = subprocess.run(["python", "ingest_db.py"], capture_output=True, text=True)
    
    if db_result.returncode != 0:
        print(f"Database Error: {db_result.stderr}")
        return jsonify({"error": "DB Ingestion failed", "details": db_result.stderr}), 500
        
    # Cleanup local files to free memory instances
    if os.path.exists(local_input_path):
        os.remove(local_input_path)

    print("Success: Pipeline complete!")
    return jsonify({"status": "Success", "file": file_name}), 200

if __name__ == "__main__":
    # Cloud Run sets the PORT env var defaulting to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
