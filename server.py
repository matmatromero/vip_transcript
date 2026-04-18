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


@app.route("/search", methods=["GET", "POST"])
def search():
    """
    RAG search endpoint. Accepts a natural language query, embeds it via Vertex AI,
    and returns the most semantically similar transcript chunks from pgvector.
    Supports both GET (query params) and POST (JSON body).
    """
    import psycopg2

    if request.method == "GET":
        query_text = request.args.get("query")
        limit = int(request.args.get("limit", 5))
        theme_filter = request.args.get("theme", None)
        speaker_filter = request.args.get("speaker", None)
        transcript_filter = request.args.get("transcript", None)
    else:
        body = request.get_json()
        if not body:
            return jsonify({"error": "Missing JSON body"}), 400
        query_text = body.get("query")
        limit = body.get("limit", 5)
        theme_filter = body.get("theme", None)
        speaker_filter = body.get("speaker", None)
        transcript_filter = body.get("transcript", None)

    if not query_text:
        return jsonify({"error": "Missing 'query' parameter"}), 400

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "tonal-transit-435411-i4")

    try:
        from chunker.embedders import VertexAIEmbedder
        embedder = VertexAIEmbedder(model="text-embedding-004", project=project_id, location="us-central1")
        query_embedding = embedder.embed([query_text])[0]
    except Exception as e:
        return jsonify({"error": "Embedding failed", "details": str(e)}), 500

    vector_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    db_config = {
        "dbname": os.environ.get("DB_NAME", "rag_db"),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASS", "password"),
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
    }

    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        where_clauses = []
        params = []

        if theme_filter:
            where_clauses.append("theme = %s")
            params.append(theme_filter)
        if speaker_filter:
            where_clauses.append("speaker_array::text ILIKE %s")
            params.append(f"%{speaker_filter}%")
        if transcript_filter:
            where_clauses.append("transcript_name = %s")
            params.append(transcript_filter)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = f"""
            SELECT chunk_id, transcript_name, section, theme,
                   speaker_array, chunk_text, token_count,
                   embedding <=> %s::vector AS distance
            FROM transcript_chunks
            {where_sql}
            ORDER BY distance
            LIMIT %s;
        """

        params = [vector_str] + params + [limit]
        # Reorder: vector_str needs to be first param, then WHERE params, then LIMIT
        # Actually, let's rebuild to be safe with param ordering
        all_params = []
        all_params.append(vector_str)
        if theme_filter:
            all_params.append(theme_filter)
        if speaker_filter:
            all_params.append(f"%{speaker_filter}%")
        if transcript_filter:
            all_params.append(transcript_filter)
        all_params.append(limit)

        cur.execute(sql, all_params)
        rows = cur.fetchall()

        results = []
        for row in rows:
            results.append({
                "chunk_id": row[0],
                "transcript_name": row[1],
                "section": row[2],
                "theme": row[3],
                "speakers": row[4],
                "chunk_text": row[5],
                "token_count": row[6],
                "distance": round(float(row[7]), 4),
            })

        cur.close()
        conn.close()

        return jsonify({
            "query": query_text,
            "results_count": len(results),
            "results": results,
        }), 200

    except Exception as e:
        return jsonify({"error": "Search failed", "details": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
