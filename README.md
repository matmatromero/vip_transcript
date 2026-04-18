# VIP Transcript — Semantic Chunking & RAG Pipeline

> A cloud-agnostic, embedding-powered pipeline that transforms raw earnings call transcripts into semantically chunked, theme-tagged, vector-indexed data — ready for Retrieval-Augmented Generation (RAG).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Core Pipeline — Module Walkthrough](#3-core-pipeline--module-walkthrough)
4. [Infrastructure & Cloud Files](#4-infrastructure--cloud-files)
5. [GCP Implementation — Start to Finish](#5-gcp-implementation--start-to-finish)
6. [Database Schema & RAG Querying](#6-database-schema--rag-querying)
7. [Local Development](#7-local-development)
8. [Configuration Reference](#8-configuration-reference)

---

## 1. Architecture Overview

The pipeline replaces a legacy multi-agent LLM chain (Agent 1 → Agent 2 → Agent 3) with a deterministic, Pythonic workflow that achieves the same result at a fraction of the cost and latency.

### Pipeline Stages

```
Raw .txt Transcript
       │
       ▼
  ┌─────────┐
  │ parser  │  Extracts speaker turns, detects Q&A section boundaries
  └────┬────┘
       ▼
  ┌──────────┐
  │ splitter │  Breaks each turn into individual sentences
  └────┬─────┘
       ▼
  ┌──────────┐
  │ embedder │  Converts every sentence into a dense float vector
  └────┬─────┘
       ▼
  ┌───────────┐
  │ segmenter │  Groups sentences into chunks based on cosine similarity
  └────┬──────┘
       ▼
  ┌───────────┐
  │  chunker  │  Assigns themes, attaches embeddings, outputs JSON
  └────┬──────┘
       ▼
  Structured JSON with themes + embeddings
       │
       ▼
  ┌────────────┐
  │ ingest_db  │  Pushes chunks into PostgreSQL (pgvector)
  └────────────┘
```

### Design Principles

- **Platform Agnostic**: The `EmbeddingModel` protocol allows swapping between SentenceTransformers (local), OpenAI, Azure OpenAI, AWS Bedrock, and Google Vertex AI without changing any core logic.
- **Pure Semantic Chunking**: Chunk boundaries are determined exclusively by vector cosine similarity — not by speaker changes or structural rules.
- **Top-Down Theme Assignment**: Themes are explicitly defined upfront and assigned via embedding similarity, not discovered via ad-hoc clustering.

---

## 2. Project Structure

```
vip_transcript/
├── chunker/                    # Core Python package
│   ├── __init__.py
│   ├── parser.py               # Stage 1: Transcript → Speaker Turns
│   ├── splitter.py             # Stage 2: Turns → Sentences
│   ├── embedders.py            # Stage 3: Sentences → Vectors (multi-provider)
│   ├── segmenter.py            # Stage 4: Vectors → Semantic Chunks
│   └── chunker.py              # Orchestrator: Runs all stages + theme assignment
│
├── server.py                   # Flask web server (Cloud Run entrypoint)
├── run_chunker.py              # CLI entrypoint for local/container execution
├── ingest_db.py                # Database ingestion script (PostgreSQL/pgvector)
├── schema.sql                  # PostgreSQL table definitions + vector indexes
│
├── Dockerfile                  # Production container (slim, no PyTorch)
├── docker-compose.yml          # Local PostgreSQL + pgvector for testing
├── cloudbuild.yaml             # Google Cloud Build config with Kaniko caching
├── requirements.txt            # Full dependencies (local dev)
├── requirements-cloud.txt      # Cloud-only dependencies (no sentence-transformers)
│
├── raw_transcripts/            # Input: raw .txt earnings call transcripts
├── output/chunks/              # Output: processed JSON chunk files
├── tests/                      # Unit tests
├── old_references/             # Legacy architecture docs for reference
│
├── GCP_ARCHITECTURE.md         # Cloud architecture design document
└── GCP_CONSOLE_DEPLOYMENT_GUIDE.md  # Step-by-step GCP Console walkthrough
```

---

## 3. Core Pipeline — Module Walkthrough

### 3.1 `chunker/parser.py` — Transcript Parser

**Purpose**: Reads a raw `.txt` transcript file and extracts structured speaker turns.

**How it works**:
1. Reads all lines from the file and strips blank lines.
2. Iterates through lines detecting **speaker name → role → spoken text** patterns using `_is_role_line()`, which uses heuristics (line length, sentence starters, punctuation) to distinguish role titles from spoken content.
3. Detects the **Q&A section boundary** using `_detect_section()`, which scans for explicit transition phrases like *"move on to investor questions"* or *"jump into Q&A"*.
4. Returns a list of turn dictionaries.

**Key code**:
```python
SECTION_QA_MARKERS = (
    "move on to investor questions",
    "jump into q&a",
    "now we will move on",
    ...
)

def parse_turns(filepath: str) -> list[dict]:
    # Returns: [{"turn_index": 0, "speaker": "Elon Musk", "role": "CEO", 
    #            "section": "prepared_remarks", "text": "..."}, ...]
```

**Input**: Raw `.txt` file path  
**Output**: `list[dict]` — each dict represents one speaker's continuous block of text

---

### 3.2 `chunker/splitter.py` — Sentence Splitter

**Purpose**: Breaks a block of spoken text into individual sentences.

**How it works**:
Uses a regex pattern that splits on sentence-ending punctuation (`.`, `!`, `?`) followed by whitespace and an uppercase letter. This preserves abbreviations and decimal numbers.

**Key code**:
```python
def split_into_sentences(text: str) -> list[str]:
    text = re.sub(r"[\r\n]+", " ", text).strip()
    pattern = r'(?<=[.!?])\s+(?=[A-Z\["\'])'
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if p.strip()]
```

**Input**: A single string of spoken text  
**Output**: `list[str]` — individual sentences

---

### 3.3 `chunker/embedders.py` — Embedding Providers

**Purpose**: Converts text strings into dense float vectors. This module implements the **platform-agnostic** design through a Python `Protocol`.

**The Protocol**:
```python
@runtime_checkable
class EmbeddingModel(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...
```

Any class that implements `embed(texts) → list[list[float]]` is automatically compatible with the entire pipeline.

**Available Providers**:

| Class | Provider | Dimensions | Use Case |
|---|---|---|---|
| `SentenceTransformerEmbedder` | HuggingFace (local) | 384 | Local dev, offline |
| `OpenAIEmbedder` | OpenAI API | 1536 | Cloud, high quality |
| `BedrockEmbedder` | AWS Bedrock | varies | AWS deployments |
| `AzureOpenAIEmbedder` | Azure OpenAI | 1536 | Enterprise Azure |
| `VertexAIEmbedder` | Google Vertex AI | 768 | GCP deployments |

**Vertex AI Batching**: Google's Vertex AI API enforces a hard limit of 250 texts per request. The `VertexAIEmbedder` automatically batches larger arrays:

```python
def embed(self, texts: list[str]) -> list[list[float]]:
    all_embeddings = []
    batch_size = 250
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = self._client.get_embeddings(batch)
        all_embeddings.extend([emb.values for emb in embeddings])
    return all_embeddings
```

---

### 3.4 `chunker/segmenter.py` — Semantic Segmenter

**Purpose**: Groups sentences into topic-coherent chunks using vector cosine similarity. This is the mathematical core of the pipeline.

**How it works**:
1. Starts with the first sentence in a new chunk.
2. For each subsequent sentence, calculates the **cosine similarity** between its embedding and the previous sentence's embedding.
3. **Decision logic**:
   - If similarity is **high** (≥ threshold) AND size limits are not exceeded → **add** the sentence to the current chunk.
   - If similarity **drops** below the threshold AND the chunk has at least `min_sentences` → **cut** the chunk (semantic boundary detected).
   - If `max_sentences` or `max_tokens` is exceeded → **force cut** regardless of similarity.
4. Each chunk records `boundary_reason`: either `"similarity_drop"`, `"max_size"`, or `"eof"`.

**Key code**:
```python
def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))

# Inside the main loop:
sim = cosine_similarity(current_embs[-1], emb)
is_semantic_break = count >= min_sentences and sim < threshold

if exceeds_max:
    flush(sim, "max_size")
elif is_semantic_break:
    flush(sim, "similarity_drop")
else:
    current_sents.append(sent)
```

**Input**: Flat list of sentence dicts + their embedding vectors  
**Output**: `list[dict]` — each dict is a chunk containing text, speakers, sentences, and similarity metadata

---

### 3.5 `chunker/chunker.py` — Pipeline Orchestrator

**Purpose**: Ties all stages together and adds **theme assignment** and **embedding serialization**.

**Theme Assignment** — How it works:
1. Five themes are explicitly defined with rich semantic descriptions:
```python
DEFAULT_THEMES = {
    "Autonomous Driving & FSD": "Autonomous driving, Full Self-Driving capabilities, Robotaxi...",
    "Financials & Deliveries": "Financial performance, operating margins, vehicle deliveries...",
    "Optimus & AI": "Optimus humanoid robot, artificial intelligence training...",
    "Production & Energy": "Manufacturing production scaling, Gigafactories, battery...",
    "Administrative & Forward-Looking": "Administrative introductions, safe harbor statements...",
}
```
2. These descriptions are embedded into vectors (the "anchor" embeddings).
3. Each chunk's text is also embedded.
4. The chunk is assigned to whichever theme has the **highest cosine similarity** to its content.

```python
for i, chunk in enumerate(chunks):
    c_emb = chunk_embs[i]
    best_sim = -1.0
    best_idx = 0
    for j, t_emb in enumerate(theme_embs):
        sim = cosine_similarity(c_emb, t_emb)
        if sim > best_sim:
            best_sim = sim
            best_idx = j
    chunk["theme"] = theme_names[best_idx]
```

**Embedding Serialization**: Each chunk's vector is saved directly into the JSON output for downstream database ingestion without re-computation.

---

### 3.6 `run_chunker.py` — CLI Interface

**Purpose**: Command-line entrypoint that wires up argument parsing to the pipeline.

**Usage**:
```bash
# Local (uses HuggingFace model, runs on CPU)
python run_chunker.py \
  --input raw_transcripts/ \
  --output output/chunks/ \
  --embedder sentence-transformers \
  --model all-MiniLM-L6-v2 \
  --threshold 0.75

# GCP (uses Vertex AI, runs serverless)
python run_chunker.py \
  --input raw_transcripts/ \
  --output output/chunks/ \
  --embedder vertexai \
  --gcp-project my-project-id \
  --gcp-location us-central1
```

**Supported flags**: `--embedder`, `--model`, `--threshold`, `--min-sentences`, `--max-sentences`, `--max-tokens`, `--api-key`, `--region`, `--endpoint`, `--deployment`, `--gcp-project`, `--gcp-location`

---

## 4. Infrastructure & Cloud Files

### 4.1 `server.py` — Cloud Run Web Server

**Purpose**: Acts as the HTTP bridge between Google Eventarc triggers and the Python pipeline.

**Flow**:
1. Listens on port `8080` via Flask + Gunicorn.
2. Receives an HTTP POST from Eventarc containing the GCS bucket name and uploaded filename.
3. Downloads the `.txt` file from GCS to the container's local filesystem.
4. Executes `run_chunker.py` as a subprocess with the `--embedder vertexai` flag.
5. Executes `ingest_db.py` to push results into PostgreSQL.
6. Cleans up local files and returns HTTP 200.

### 4.2 `ingest_db.py` — Database Ingestion

**Purpose**: Reads processed JSON chunk files and inserts them into PostgreSQL with pgvector.

**Key details**:
- Connection uses **environment variables** (`DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME`) set in Cloud Run, falling back to localhost defaults for local development.
- Embeddings are serialized as pgvector-compatible string arrays: `"[0.123, -0.456, ...]"`.
- Uses `ON CONFLICT (chunk_id) DO NOTHING` to safely handle re-processing without duplicates.
- Speaker arrays are stored as native PostgreSQL `JSONB`.

### 4.3 `schema.sql` — Database Schema

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS transcript_chunks (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(100) UNIQUE NOT NULL,     -- e.g. "tesla_Q1_chunk_007"
    transcript_name VARCHAR(100) NOT NULL,     -- e.g. "tesla_Q1"
    section VARCHAR(50),                       -- "prepared_remarks" or "qa"
    theme VARCHAR(100),                        -- e.g. "Optimus & AI"
    speaker_array JSONB,                       -- [{"name": "Elon Musk", "role": "CEO"}]
    chunk_text TEXT NOT NULL,                   -- The full concatenated chunk text
    token_count INT,
    embedding vector(768)                      -- Vertex AI = 768 dimensions
);

-- HNSW index for fast approximate nearest-neighbor vector search
CREATE INDEX IF NOT EXISTS embedding_idx 
    ON transcript_chunks USING hnsw (embedding vector_cosine_ops);

-- Standard B-tree indexes for SQL WHERE filtering
CREATE INDEX IF NOT EXISTS idx_transcript_name ON transcript_chunks(transcript_name);
CREATE INDEX IF NOT EXISTS idx_theme ON transcript_chunks(theme);
```

### 4.4 `Dockerfile` — Production Container

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt
RUN mkdir -p raw_transcripts output/chunks

COPY chunker /app/chunker
COPY run_chunker.py /app/run_chunker.py
COPY ingest_db.py /app/ingest_db.py
COPY schema.sql /app/schema.sql
COPY server.py /app/server.py

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 server:app
```

**Key optimization**: Uses `requirements-cloud.txt` instead of `requirements.txt`. This excludes `sentence-transformers` (and its transitive dependency PyTorch, ~2GB), since Cloud Run uses Vertex AI for embeddings. This reduced build times from **~12 minutes to ~2 minutes**.

### 4.5 `cloudbuild.yaml` — Kaniko Cache

```yaml
steps:
  - name: 'gcr.io/kaniko-project/executor:latest'
    args:
      - '--dockerfile=Dockerfile'
      - '--context=.'
      - '--destination=${_IMAGE_NAME}'
      - '--cache=true'
      - '--cache-ttl=168h'
```

Enables Docker layer caching across builds. When only application code changes (not dependencies), subsequent builds complete in **~30–60 seconds**.

---

## 5. GCP Implementation — Start to Finish

This section documents the complete journey of deploying the pipeline to Google Cloud Platform.

### Step 1: Local Development & Validation

The pipeline was first built and validated entirely on a local Mac:
- Used `SentenceTransformerEmbedder` (HuggingFace `all-MiniLM-L6-v2`, 384 dimensions) for offline embedding.
- Processed 4 Tesla earnings call transcripts (Q1–Q4), producing ~735 semantic chunks total.
- Validated theme assignment across all quarters.
- All 12 unit tests passed.

### Step 2: Code Pushed to GitHub

```bash
git init
git remote add origin git@github.com:matmatromero/vip_transcript.git
git add . && git commit -m "Initial commit"
git push -u origin main -f
```

SSH was used instead of HTTPS to bypass credential conflicts on the local machine.

### Step 3: GCP Infrastructure Setup (Console UI)

All infrastructure was provisioned through the Google Cloud Console web interface:

1. **Cloud Storage**: Created a bucket named `raw_transcripts` for uploading `.txt` files.
2. **Cloud SQL**: Created a PostgreSQL instance (`rag-database`) in `us-central1`.
   - Ran `schema.sql` via **Cloud SQL Studio** (browser-based SQL editor).
   - Enabled public IP and authorized `0.0.0.0/0` under **Connections → Authorized Networks** to allow Cloud Run access.
3. **Vertex AI API**: Enabled via the API Library page.

### Step 4: Cloud Run Deployment

1. Navigated to **Cloud Run → Deploy Container → Service**.
2. Selected **Continuously deploy from a source repository**.
3. Authenticated GitHub and pointed to `matmatromero/vip_transcript`.
4. Under Build Configuration, selected **Dockerfile** at path `/Dockerfile`.
5. Set container memory to **2 GiB** (required for Vertex AI SDK overhead).
6. Added environment variables under **Variables & Secrets**:
   - `DB_HOST` = `34.171.50.91` (Cloud SQL public IP)
   - `DB_USER` = `postgres`
   - `DB_PASS` = *(instance password)*
   - `DB_NAME` = `rag_db`

### Step 5: Eventarc Trigger

1. Inside the Cloud Run service, clicked **+ ADD EVENTARC TRIGGER**.
2. Set **Event Provider** to `Cloud Storage`.
3. Set **Event Type** to `google.cloud.storage.object.v1.finalized`.
4. Selected the `raw_transcripts` bucket.
5. Saved the trigger.

### Step 6: Issues Encountered & Resolved

| Issue | Root Cause | Fix |
|---|---|---|
| Container failed to start on port 8080 | Dockerfile ran `run_chunker.py` and exited — Cloud Run expects a persistent web server | Created `server.py` (Flask + Gunicorn) as a persistent HTTP listener |
| Memory limit of 512 MiB exceeded | Default Cloud Run allocation too small for Vertex AI SDK | Increased memory to 2 GiB in Cloud Run container settings |
| Vertex AI: "250 instances allowed, got 723" | Google's embedding API has a hard batch limit of 250 texts per request | Added manual batching loop in `VertexAIEmbedder.embed()` |
| Connection timed out to Cloud SQL | Cloud SQL blocks all external IPs by default | Added `0.0.0.0/0` to Cloud SQL Authorized Networks |
| Expected 384 dimensions, not 768 | Schema was built for local model (384d) but Vertex AI produces 768d vectors | Dropped and recreated table with `vector(768)` |
| Database silently failing | `ingest_db.py` had hardcoded `localhost` and swallowed connection errors | Changed to `os.environ.get()` with Cloud Run env vars; added `sys.exit(1)` on failure |
| Builds taking 12–13 minutes | Installing sentence-transformers/PyTorch (~2GB) on every build | Created `requirements-cloud.txt` (no PyTorch) + `cloudbuild.yaml` with Kaniko caching |

### Step 7: End-to-End Test

After all fixes:
1. Uploaded `tesla_Q1.txt` to the `raw_transcripts` GCS bucket via the Console UI.
2. Eventarc triggered Cloud Run within seconds.
3. Cloud Run downloaded the file, processed it through the semantic chunker, hit Vertex AI for embeddings, assigned themes, and pushed 241 chunks into Cloud SQL.
4. Verified data appeared in PostgreSQL via Cloud SQL Studio:
   ```sql
   SELECT chunk_id, theme, chunk_text FROM transcript_chunks LIMIT 5;
   ```

---

## 6. Database Schema & RAG Querying

### How RAG Lookups Work

When a user asks: *"What did Travis Axelrod say about AI in the beginning?"*

1. **Embed the query**: The question is converted to a 768-dimensional vector using Vertex AI.
2. **Vector search with filters**: A SQL query searches for the nearest vectors, filtered by speaker and section:
   ```sql
   SELECT chunk_id, theme, chunk_text,
          embedding <=> '[query_vector]' AS distance
   FROM transcript_chunks
   WHERE speaker_array @> '[{"name": "Travis Axelrod"}]'
     AND section = 'prepared_remarks'
   ORDER BY distance
   LIMIT 5;
   ```
3. **Return to LLM**: The top chunks are passed to an LLM (e.g., Gemini, GPT-4) as context to generate the final answer.

---

## 7. Local Development

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the Pipeline Locally
```bash
python run_chunker.py \
  --input raw_transcripts/ \
  --output output/chunks/ \
  --embedder sentence-transformers \
  --model all-MiniLM-L6-v2
```

### Run Tests
```bash
pytest tests/ -v
```

### Local PostgreSQL (Optional)
```bash
docker compose up -d
python ingest_db.py
```

---

## 8. Configuration Reference

### Chunking Parameters

| Parameter | Default | Description |
|---|---|---|
| `--threshold` | `0.75` | Cosine similarity threshold. Lower = fewer, larger chunks. Higher = more, smaller chunks. |
| `--min-sentences` | `3` | Minimum sentences before a semantic break is allowed. |
| `--max-sentences` | `15` | Force-cut a chunk after this many sentences regardless of similarity. |
| `--max-tokens` | `400` | Force-cut a chunk if estimated token count exceeds this. |

### Environment Variables (Cloud Run)

| Variable | Description |
|---|---|
| `DB_HOST` | Cloud SQL public IP address |
| `DB_USER` | PostgreSQL username (default: `postgres`) |
| `DB_PASS` | PostgreSQL password |
| `DB_NAME` | Database name (default: `rag_db`) |
| `DB_PORT` | PostgreSQL port (default: `5432`) |
| `PORT` | Cloud Run listening port (auto-set to `8080`) |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (auto-set by Cloud Run) |
