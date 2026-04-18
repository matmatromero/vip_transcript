import pytest
from pathlib import Path

from chunker.parser import parse_turns
from chunker.splitter import split_into_sentences
from chunker.segmenter import cosine_similarity, segment

TRANSCRIPT_DIR = Path(__file__).parent.parent / "raw_transcripts"
SAMPLE_TRANSCRIPT = TRANSCRIPT_DIR / "tesla_Q1.txt"


class IdentityEmbedder:
    def __init__(self, dim: int = 8):
        self._dim = dim
        self._counter = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for _ in texts:
            vec = [0.0] * self._dim
            vec[self._counter % self._dim] = 1.0
            self._counter += 1
            results.append(vec)
        return results

    def __str__(self) -> str:
        return "IdentityEmbedder"


class ConstantEmbedder:
    def __init__(self, value: float = 1.0, dim: int = 8):
        self._vec = [value] * dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec[:] for _ in texts]

    def __str__(self) -> str:
        return "ConstantEmbedder"


def test_parse_turns_returns_correct_fields():
    turns = parse_turns(str(SAMPLE_TRANSCRIPT))
    assert len(turns) > 0
    for turn in turns:
        assert "turn_index" in turn
        assert "speaker" in turn
        assert "role" in turn
        assert "section" in turn
        assert "text" in turn
        assert turn["section"] in ("prepared_remarks", "qa")


def test_parse_turns_section_transitions():
    turns = parse_turns(str(SAMPLE_TRANSCRIPT))
    sections = [t["section"] for t in turns]
    assert "prepared_remarks" in sections
    assert "qa" in sections
    first_qa = sections.index("qa")
    assert all(s == "prepared_remarks" for s in sections[:first_qa])
    assert all(s == "qa" for s in sections[first_qa:])


def test_split_into_sentences_basic():
    text = "Hello world. This is a test. Is it working?"
    sentences = split_into_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "Hello world."
    assert sentences[2] == "Is it working?"


def test_split_into_sentences_preserves_content():
    turns = parse_turns(str(SAMPLE_TRANSCRIPT))
    for turn in turns[:10]:
        sentences = split_into_sentences(turn["text"])
        assert len(sentences) >= 1
        for s in sentences:
            assert len(s.strip()) > 0


def test_cosine_similarity_identical_vectors():
    vec = [1.0, 0.0, 0.0]
    assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-5)


def test_cosine_similarity_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-5)


def test_cosine_similarity_zero_vector():
    a = [0.0, 0.0]
    b = [1.0, 0.0]
    assert cosine_similarity(a, b) == 0.0


def test_segment_respects_min_sentences():
    sentences = [
        {"sent_index": i, "speaker": "Speaker A", "role": "", "section": "qa", "text": f"Sentence {i}."}
        for i in range(20)
    ]
    embedder = IdentityEmbedder(dim=20)
    embeddings = embedder.embed([s["text"] for s in sentences])

    chunks = segment(
        sentences=sentences,
        embeddings=embeddings,
        threshold=0.99,
        min_sentences=3,
        max_sentences=15,
        max_tokens=400,
    )

    for chunk in chunks[:-1]:
        assert chunk["sentence_count"] >= 3


def test_segment_respects_max_sentences():
    sentences = [
        {"sent_index": i, "speaker": "Speaker A", "role": "", "section": "qa", "text": f"Sentence {i}."}
        for i in range(50)
    ]
    embedder = ConstantEmbedder()
    embeddings = embedder.embed([s["text"] for s in sentences])

    chunks = segment(
        sentences=sentences,
        embeddings=embeddings,
        threshold=0.0,
        min_sentences=1,
        max_sentences=10,
        max_tokens=9999,
    )

    for chunk in chunks:
        assert chunk["sentence_count"] <= 10


def test_no_information_loss():
    turns = parse_turns(str(SAMPLE_TRANSCRIPT))

    flat_sentences: list[dict] = []
    sent_index = 0
    for turn in turns:
        for text in split_into_sentences(turn["text"]):
            flat_sentences.append({
                "sent_index": sent_index,
                "speaker": turn["speaker"],
                "role": turn["role"],
                "section": turn["section"],
                "text": text,
            })
            sent_index += 1

    embedder = ConstantEmbedder()
    embeddings = embedder.embed([s["text"] for s in flat_sentences])

    chunks = segment(
        sentences=flat_sentences,
        embeddings=embeddings,
        threshold=0.5,
        min_sentences=3,
        max_sentences=15,
        max_tokens=400,
    )

    all_sent_indices = []
    for chunk in chunks:
        for sent in chunk["sentences"]:
            all_sent_indices.append(sent["sent_index"])

    assert sorted(all_sent_indices) == list(range(len(flat_sentences)))


def test_qa_integrity_chunks_contain_multiple_speakers():
    turns = parse_turns(str(SAMPLE_TRANSCRIPT))

    flat_sentences: list[dict] = []
    sent_index = 0
    for turn in turns:
        for text in split_into_sentences(turn["text"]):
            flat_sentences.append({
                "sent_index": sent_index,
                "speaker": turn["speaker"],
                "role": turn["role"],
                "section": turn["section"],
                "text": text,
            })
            sent_index += 1

    embedder = ConstantEmbedder()
    embeddings = embedder.embed([s["text"] for s in flat_sentences])

    chunks = segment(
        sentences=flat_sentences,
        embeddings=embeddings,
        threshold=0.5,
        min_sentences=3,
        max_sentences=15,
        max_tokens=400,
    )

    qa_chunks = [c for c in chunks if c["section"] == "qa"]
    multi_speaker_qa = [c for c in qa_chunks if len(c["speakers"]) > 1]
    assert len(multi_speaker_qa) > 0


def test_boundary_reason_values_are_valid():
    valid_reasons = {"similarity_drop", "max_size", "eof"}

    turns = parse_turns(str(SAMPLE_TRANSCRIPT))
    flat_sentences: list[dict] = []
    sent_index = 0
    for turn in turns:
        for text in split_into_sentences(turn["text"]):
            flat_sentences.append({
                "sent_index": sent_index,
                "speaker": turn["speaker"],
                "role": turn["role"],
                "section": turn["section"],
                "text": text,
            })
            sent_index += 1

    embedder = ConstantEmbedder()
    embeddings = embedder.embed([s["text"] for s in flat_sentences])

    chunks = segment(
        sentences=flat_sentences,
        embeddings=embeddings,
        threshold=0.5,
        min_sentences=3,
        max_sentences=15,
        max_tokens=400,
    )

    for chunk in chunks:
        assert chunk["boundary_reason"] in valid_reasons
