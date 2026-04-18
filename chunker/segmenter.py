import numpy as np


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def estimate_tokens(text: str) -> int:
    return len(text.split()) * 4 // 3


def segment(
    sentences: list[dict],
    embeddings: list[list[float]],
    threshold: float,
    min_sentences: int,
    max_sentences: int,
    max_tokens: int,
) -> list[dict]:
    chunks = []
    current_sents: list[dict] = []
    current_embs: list[list[float]] = []

    def flush(boundary_sim: float | None, reason: str) -> None:
        if not current_sents:
            return

        seen: set[str] = set()
        speakers = []
        for s in current_sents:
            if s["speaker"] not in seen:
                seen.add(s["speaker"])
                speakers.append({"name": s["speaker"], "role": s.get("role", "")})

        text = " ".join(s["text"] for s in current_sents)
        within_sims = [
            cosine_similarity(current_embs[j], current_embs[j + 1])
            for j in range(len(current_embs) - 1)
        ]

        chunks.append({
            "section": current_sents[0]["section"],
            "speakers": speakers,
            "sentence_count": len(current_sents),
            "token_count": estimate_tokens(text),
            "text": text,
            "sentences": [
                {
                    "sent_index": s["sent_index"],
                    "speaker": s["speaker"],
                    "text": s["text"],
                }
                for s in current_sents
            ],
            "similarity_scores": within_sims,
            "boundary_similarity": boundary_sim,
            "boundary_reason": reason,
        })

    for sent, emb in zip(sentences, embeddings):
        if not current_sents:
            current_sents.append(sent)
            current_embs.append(emb)
            continue

        sim = cosine_similarity(current_embs[-1], emb)
        projected_text = " ".join(s["text"] for s in current_sents) + " " + sent["text"]
        count = len(current_sents)

        exceeds_max = count >= max_sentences or estimate_tokens(projected_text) >= max_tokens
        is_semantic_break = count >= min_sentences and sim < threshold

        if exceeds_max:
            flush(sim, "max_size")
            current_sents = [sent]
            current_embs = [emb]
        elif is_semantic_break:
            flush(sim, "similarity_drop")
            current_sents = [sent]
            current_embs = [emb]
        else:
            current_sents.append(sent)
            current_embs.append(emb)

    flush(None, "eof")
    return chunks
