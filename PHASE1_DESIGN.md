# Phase 1 Design: Semantic Chunking
## Earnings Call Transcript Analyzer — Reimplementation

---

## 1. Objective

Replace the old pipeline's naive, structure-based chunking with **semantic chunking** —
grouping text by *meaning* rather than by speaker turns, paragraphs, or fixed token counts.

This is Phase 1 only. No LLM calls. No theme extraction. No scoring.
The output of this phase feeds directly into Phase 2 (theme extraction).

---

## 2. Design Principles

| Principle | What It Means |
|---|---|
| **Transcript agnostic** | The chunker makes no assumptions about topic, company, or industry |
| **Platform agnostic** | Embedding model is a pluggable dependency — swap local/cloud/API freely |
| **No agent overhead** | Pure Python functions, no Azure threads, no LLM round-trips in this phase |
| **Incrementally testable** | Each stage produces inspectable output before proceeding |

---

## 3. Understanding the Input

### 3.1 Transcript Format

The raw transcripts follow a strict 3-line-per-turn pattern:

```
Speaker Name
Speaker Role/Title
[Full dialogue block — sometimes 2,500+ words in a single line]
```

### 3.2 Two Structural Sections

Every call has two logically distinct sections with very different chunking challenges:

| Section | Characteristics | Chunking Risk |
|---|---|---|
| **Prepared Remarks** | Single speaker, long monologue, topic shifts mid-speech | One giant block becomes one entire chunk |
| **Q&A** | Multi-speaker, rapid back-and-forth, questions and answers semantically coupled | Question and answer from different speakers split into separate unrelated chunks |

The old approach failed specifically on Q&A: an analyst question about "robotaxi risks"
and four executives each contributing 2–3 sentences of answer were processed as five
separate micro-chunks, creating duplicate or fragmented themes downstream.

### 3.3 Scale (Current Data)

- 4 transcripts (Tesla Q1–Q4)
- ~218KB total, ~900 lines
- Q1 alone: ~70KB, 361 lines

---

## 4. Chunking Strategy

### 4.1 Pipeline — Four Sequential Steps

```
Raw .txt file
     │
     ▼
[Step 1] Parse
     │  Structured speaker turns with metadata
     ▼
[Step 2] Sentence Splitting
     │  Flat list of sentences, each tagged with speaker + section
     ▼
[Step 3] Embed
     │  Sentence vectors via pluggable embedding model
     ▼
[Step 4] Segment by Semantic Similarity
     │  Group sentences into coherent chunks
     ▼
Structured JSON output
```

---

### Step 1 — Parse: Speaker Turns

Parse each transcript into a list of atomic utterances with full provenance metadata:

```python
[
  {
    "turn_index": 0,
    "speaker": "Travis Axelrod",
    "role": "Head of Investor Relations",
    "section": "prepared_remarks",  # or "qa"
    "text": "Good afternoon, everyone..."
  },
  ...
]
```

**Section detection rule:** The moderator's first question mark after opening remarks
triggers `section = "qa"` for all subsequent turns.

---

### Step 2 — Sentence Splitting

Split each dialogue block into individual sentences.
Each sentence inherits its parent turn's metadata.

```python
[
  {
    "sent_index": 0,
    "turn_index": 0,
    "speaker": "Travis Axelrod",
    "role": "Head of Investor Relations",
    "section": "prepared_remarks",
    "text": "Good afternoon, everyone, and welcome to Tesla's First Quarter 2025 Q&A Webcast."
  },
  ...
]
```

---

### Step 3 — Embed (Platform-Agnostic Interface)

The embedding model is a **pluggable dependency** injected at runtime:

```python
# Contract: any embedder must implement this interface
class EmbeddingModel(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...
```

Out-of-the-box adapters provided:

| Adapter | Use Case |
|---|---|
| `SentenceTransformerEmbedder(model_name)` | Local, free, offline — default |
| `OpenAIEmbedder(model_name, api_key)` | OpenAI API |
| `BedrockEmbedder(model_id, region)` | AWS Bedrock |
| `AzureOpenAIEmbedder(endpoint, key, deployment)` | Azure OpenAI |

**Usage:**
```python
# Swap embedder with a single line — nothing else changes
chunker = SemanticChunker(embedder=SentenceTransformerEmbedder("all-MiniLM-L6-v2"))
chunker = SemanticChunker(embedder=OpenAIEmbedder("text-embedding-3-small"))
chunker = SemanticChunker(embedder=BedrockEmbedder("amazon.titan-embed-text-v2:0"))
```

---

### Step 4 — Segment by Semantic Similarity

Use **cosine similarity between consecutive sentence embeddings** to detect topic boundaries.

```
sim(sent_i, sent_i+1) < threshold  →  topic boundary  →  start new chunk
```

Additional constraints (all configurable):
- `min_sentences_per_chunk` — avoid micro-chunks (default: 3)
- `max_sentences_per_chunk` — avoid context overflow (default: 15)
- `max_tokens_per_chunk` — hard ceiling for LLM compatibility (default: 400)
- **Hard break on moderator transitions** — when the IR moderator introduces a new
  question, force a chunk boundary regardless of similarity score

> **Note on threshold:** Similarity threshold is a configurable parameter.
> Tuning is explicitly deferred to post-Phase-1 analysis.
> Default starting point: `0.75`.

---

## 5. Output Schema

Each transcript produces one JSON file.
The structure is designed as a **clean input for Phase 2 theme extraction** —
directly replacing the raw text fed into the old Agent 1, but with far richer context.

```json
{
  "transcript_id": "tesla_Q1",
  "source_file": "tesla_Q1.txt",
  "processing_metadata": {
    "embedder": "SentenceTransformerEmbedder/all-MiniLM-L6-v2",
    "similarity_threshold": 0.75,
    "min_sentences": 3,
    "max_sentences": 15,
    "max_tokens": 400
  },
  "chunks": [
    {
      "chunk_id": "tesla_Q1_chunk_001",
      "chunk_index": 0,
      "section": "prepared_remarks",
      "speakers": [
        {"name": "Elon Musk", "role": "CEO & Director"}
      ],
      "sentence_count": 7,
      "token_count": 312,
      "text": "Full concatenated text of the chunk...",
      "sentences": [
        {
          "sent_index": 0,
          "speaker": "Elon Musk",
          "text": "Individual sentence text..."
        }
      ],
      "similarity_scores": [0.88, 0.91, 0.72, 0.84, 0.90, 0.65],
      "boundary_similarity": 0.61,
      "boundary_reason": "similarity_drop"
    }
  ],
  "stats": {
    "total_chunks": 42,
    "total_sentences": 310,
    "avg_sentences_per_chunk": 7.4,
    "avg_tokens_per_chunk": 285,
    "prepared_remarks_chunks": 18,
    "qa_chunks": 24
  }
}
```

**Key design choices:**
- `similarity_scores` — cosine similarity between *consecutive sentences within* a chunk;
  enables threshold analysis later
- `boundary_similarity` — the score that *triggered* the boundary; critical for tuning
- `boundary_reason` — `similarity_drop` | `max_size` | `moderator_transition` | `eof`
- `speakers` — a list, not single value; supports multi-speaker Q&A chunks naturally
- `section` — downstream processing can treat prepared remarks vs Q&A differently

---

## 6. Success Criteria

Derived from the architecture doc and meeting minutes:

### 6.1 Semantic Coherence
All sentences in a chunk discuss the same strategic topic.
*Test: Read any chunk in isolation — it should feel like a complete, self-contained
discussion of one subject.*

### 6.2 Q&A Integrity
An analyst's question and the executive(s)' answer appear in the same chunk.
*Test: No chunk contains only a question with no answer, or only an answer with no
question, unless it is a monologue section.*

### 6.3 Size Sanity
No chunk is too small (< 3 sentences) or too large (> 400 tokens).
*Test: Inspect `stats.avg_sentences_per_chunk` and the distribution.*

### 6.4 Cross-Quarter Consistency
Chunks from Q1 and Q2 discussing the same topic (e.g., "robotaxi launch") should
produce similar embedding centroids.
*Test: Average sentence embeddings within a chunk. Same-topic chunks across quarters
should have high mutual cosine similarity — validating deduplication readiness without
the old Agent 6's expensive LLM multi-message workflow.*

### 6.5 No Information Loss
Every sentence from the original transcript appears in exactly one chunk.
*Test: Reconstruct the transcript from chunks and diff against original.*

---

## 7. Project Structure

```
vip_transcript/
├── raw_transcripts/            # Input: Q1-Q4 .txt files (unchanged)
├── chunker/
│   ├── __init__.py
│   ├── parser.py               # Step 1: Parse speaker turns + section detection
│   ├── splitter.py             # Step 2: Sentence splitting
│   ├── embedders.py            # Step 3: EmbeddingModel Protocol + all adapters
│   ├── segmenter.py            # Step 4: Cosine-similarity segmentation logic
│   └── chunker.py              # Orchestrator: runs steps 1-4, writes JSON output
├── output/
│   └── chunks/                 # One JSON per transcript
├── tests/
│   └── test_chunker.py         # Tests mapped to success criteria 6.1-6.5
├── run_chunker.py              # CLI entrypoint
└── old_references/             # Unchanged reference material
```

---

## 8. CLI Interface

```bash
# Local embedder (default, no API key needed)
python run_chunker.py \
  --input raw_transcripts/ \
  --output output/chunks/ \
  --embedder sentence-transformers \
  --model all-MiniLM-L6-v2 \
  --threshold 0.75

# OpenAI
python run_chunker.py \
  --input raw_transcripts/ \
  --embedder openai \
  --model text-embedding-3-small \
  --api-key $OPENAI_API_KEY

# AWS Bedrock
python run_chunker.py \
  --input raw_transcripts/ \
  --embedder bedrock \
  --model amazon.titan-embed-text-v2:0 \
  --region us-east-1

# Azure OpenAI
python run_chunker.py \
  --input raw_transcripts/ \
  --embedder azure \
  --deployment my-embedding-deployment \
  --endpoint $AZURE_OPENAI_ENDPOINT \
  --api-key $AZURE_OPENAI_KEY
```

---

## 9. Out of Scope for Phase 1

- No LLM calls of any kind
- No theme extraction
- No dimension tagging
- No scoring or weighting
- No agent frameworks (LangChain, ADK, etc.)
- No cloud deployment
- No threshold tuning (deferred to Phase 2 analysis)

---

## 10. Open Items for Review

| # | Item | Default / Proposal |
|---|---|---|
| 1 | Default local model | `all-MiniLM-L6-v2` (fast, 80MB, no API cost) |
| 2 | Hard break triggers | Moderator turn + max size exceeded — any others? |
| 3 | Store `boundary_similarity` per chunk? | Yes — needed for threshold tuning in Phase 2 |
| 4 | Store chunk centroid embedding? | Optional — adds file size but enables cross-quarter similarity checks without re-embedding |
