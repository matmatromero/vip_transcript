-- Enable the pgvector extension to support embedding queries
CREATE EXTENSION IF NOT EXISTS vector;

-- Table to store semantic chunks and their vectors
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(100) UNIQUE NOT NULL,
    transcript_name VARCHAR(100) NOT NULL,
    section VARCHAR(50),
    theme VARCHAR(100),
    speaker_array JSONB,          -- Store multiple speakers dynamically
    chunk_text TEXT NOT NULL,
    token_count INT,
    embedding vector(384)         -- Matches the dimension size of all-MiniLM-L6-v2
);

-- Index for optimized vector search using Inner Product (good for normalized vectors / cosine sim)
CREATE INDEX IF NOT EXISTS embedding_idx ON transcript_chunks USING hnsw (embedding vector_cosine_ops);

-- Standard indexes for quick filtering
CREATE INDEX IF NOT EXISTS idx_transcript_name ON transcript_chunks(transcript_name);
CREATE INDEX IF NOT EXISTS idx_theme ON transcript_chunks(theme);
