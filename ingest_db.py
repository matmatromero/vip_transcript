import os
import sys
import json
import psycopg2
from psycopg2.extras import Json
from pathlib import Path

# Use environment variables set in Cloud Run, falling back to local Docker defaults
DB_CONFIG = {
    "dbname": os.environ.get("DB_NAME", "rag_db"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASS", "password"),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432")
}

def setup_database(conn):
    """Initializes the schema if it doesn't exist."""
    print("Initializing database schema...")
    with conn.cursor() as cur:
        schema_path = Path("schema.sql")
        if schema_path.exists():
            cur.execute(schema_path.read_text())
            conn.commit()
            print("Schema executed via schema.sql")
        else:
            print("schema.sql not found!")

def insert_chunks(conn, file_path):
    """Reads a chunk JSON file and inserts it directly into pgvector."""
    # We do not use the raw path stem for transcript name, we'll store something cleaner
    transcript_name = file_path.name.replace("_chunks.json", "")
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    insert_query = """
        INSERT INTO transcript_chunks 
        (chunk_id, transcript_name, section, theme, speaker_array, chunk_text, token_count, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chunk_id) DO NOTHING;
    """

    inserted = 0
    with conn.cursor() as cur:
        for chunk in data["chunks"]:
            # Ensure the embedding floats match what pgvector expects (strings of formatted arrays like '[0.1, 0.2]')
            # Psycopg2 has a pgvector extension, but casting to python string representation works natively
            vector_str = "[" + ",".join(map(str, chunk["embedding"])) + "]"
            
            cur.execute(insert_query, (
                chunk["chunk_id"],
                transcript_name,
                chunk["section"],
                chunk["theme"],
                Json(chunk["speakers"]), # Safely handles the jsonb array mapping
                chunk["text"],
                chunk["token_count"],
                vector_str
            ))
            inserted += cur.rowcount
            
    conn.commit()
    print(f"Successfully inserted {inserted} chunks from {transcript_name}.")


def main():
    print("Connecting to pgvector database...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        setup_database(conn)
        
        # Load all JSON artifacts generated in output/chunks
        json_files = list(Path("output/chunks").glob("*_chunks.json"))
        print(f"Found {len(json_files)} artifacts to ingest.")
        
        for file in json_files:
            insert_chunks(conn, file)
            
        # Verify db insertion via query
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM transcript_chunks;")
            count = cur.fetchone()[0]
            print(f"\n✅ Total Chunks securely stored in postgres: {count}")
            
    except Exception as e:
        print(f"Database ingestion error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
