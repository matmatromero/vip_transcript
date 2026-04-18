import json
from pathlib import Path

from .embedders import EmbeddingModel
from .parser import parse_turns
from .segmenter import segment, cosine_similarity
from .splitter import split_into_sentences

DEFAULT_THEMES = {
    "Autonomous Driving & FSD": "Autonomous driving, Full Self-Driving capabilities, Robotaxi, autopilot, and regulatory approvals",
    "Financials & Deliveries": "Financial performance, operating margins, vehicle deliveries, cost of goods sold, revenue, and pricing strategies",
    "Optimus & AI": "Optimus humanoid robot, artificial intelligence training, supercomputers, and inference compute capabilities",
    "Production & Energy": "Manufacturing production scaling, Gigafactories, battery energy storage, solar, and supply chain constraints",
    "Administrative & Forward-Looking": "Administrative introductions, questions and answers, safe harbor statements, and forward-looking risks"
}


def process_transcript(
    filepath: str,
    embedder: EmbeddingModel,
    threshold: float = 0.75,
    min_sentences: int = 3,
    max_sentences: int = 15,
    max_tokens: int = 400,
) -> dict:
    source = Path(filepath)
    transcript_id = source.stem

    turns = parse_turns(str(source))

    flat_sentences: list[dict] = []
    sent_index = 0
    for turn in turns:
        for sentence_text in split_into_sentences(turn["text"]):
            flat_sentences.append({
                "sent_index": sent_index,
                "turn_index": turn["turn_index"],
                "speaker": turn["speaker"],
                "role": turn["role"],
                "section": turn["section"],
                "text": sentence_text,
            })
            sent_index += 1

    texts = [s["text"] for s in flat_sentences]
    embeddings = embedder.embed(texts)

    raw_chunks = segment(
        sentences=flat_sentences,
        embeddings=embeddings,
        threshold=threshold,
        min_sentences=min_sentences,
        max_sentences=max_sentences,
        max_tokens=max_tokens,
    )

    chunks = [
        {"chunk_id": f"{transcript_id}_chunk_{i + 1:03d}", "chunk_index": i, **chunk}
        for i, chunk in enumerate(raw_chunks)
    ]

    # Theme Assignment
    theme_names = list(DEFAULT_THEMES.keys())
    theme_descriptions = list(DEFAULT_THEMES.values())
    theme_embs = embedder.embed(theme_descriptions)
    
    chunk_texts = [c["text"] for c in chunks]
    chunk_embs = embedder.embed(chunk_texts)
    
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
        
        # Save the vector for downstream VectorDB / RAG querying
        # Ensure it is a standard python list of floats for JSON serialization
        if hasattr(c_emb, "tolist"):
            chunk["embedding"] = c_emb.tolist()
        else:
            chunk["embedding"] = [float(x) for x in c_emb]

    total_sents = sum(c["sentence_count"] for c in chunks)
    total_tokens = sum(c["token_count"] for c in chunks)
    prepared_count = sum(1 for c in chunks if c["section"] == "prepared_remarks")
    qa_count = sum(1 for c in chunks if c["section"] == "qa")

    return {
        "transcript_id": transcript_id,
        "source_file": source.name,
        "processing_metadata": {
            "embedder": str(embedder),
            "similarity_threshold": threshold,
            "min_sentences": min_sentences,
            "max_sentences": max_sentences,
            "max_tokens": max_tokens,
        },
        "chunks": chunks,
        "stats": {
            "total_chunks": len(chunks),
            "total_sentences": total_sents,
            "avg_sentences_per_chunk": round(total_sents / len(chunks), 1) if chunks else 0,
            "avg_tokens_per_chunk": round(total_tokens / len(chunks), 1) if chunks else 0,
            "prepared_remarks_chunks": prepared_count,
            "qa_chunks": qa_count,
        },
    }


def run(
    input_dir: str,
    output_dir: str,
    embedder: EmbeddingModel,
    threshold: float = 0.75,
    min_sentences: int = 3,
    max_sentences: int = 15,
    max_tokens: int = 400,
) -> None:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    transcript_files = sorted(input_path.glob("*.txt"))
    if not transcript_files:
        print(f"No .txt files found in {input_dir}")
        return

    for filepath in transcript_files:
        print(f"Processing {filepath.name}...")
        result = process_transcript(
            filepath=str(filepath),
            embedder=embedder,
            threshold=threshold,
            min_sentences=min_sentences,
            max_sentences=max_sentences,
            max_tokens=max_tokens,
        )

        output_file = output_path / f"{filepath.stem}_chunks.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        stats = result["stats"]
        print(
            f"  → {stats['total_chunks']} chunks | "
            f"{stats['total_sentences']} sentences | "
            f"avg {stats['avg_sentences_per_chunk']} sent/chunk | "
            f"avg {stats['avg_tokens_per_chunk']} tokens/chunk"
        )
        print(f"  → Saved: {output_file}")
