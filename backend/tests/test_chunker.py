"""Policy chunker tests."""

import pytest

from app.rag.chunker import PolicyChunker, RawPolicy
from dataclasses import FrozenInstanceError

def make_policy(sections: list[dict]) -> RawPolicy:
    return RawPolicy(
        external_id="test-policy-1",
        title="Test Policy",
        url="https://example.test/policy?id=1",
        crawled_at="2026-01-01T00:00:00Z",
        sections=sections,
    )


# ────────────────────────────────────────────────────────────────────────
# Basic behavior
# ────────────────────────────────────────────────────────────────────────


def test_single_small_section_creates_one_chunk():
    chunker = PolicyChunker(max_characters=3200, overlap_characters=400)
    policy = make_policy([{"heading": "Intro", "text": "Hello world."}])

    chunks = chunker.chunk(policy)

    assert len(chunks) == 1
    assert "Intro" in chunks[0].text
    assert "Hello world." in chunks[0].text


def test_empty_section_is_skipped():
    chunker = PolicyChunker()
    policy = make_policy(
        [
            {"heading": "Intro", "text": ""},
            {"heading": "Body", "text": "Real content."},
        ]
    )

    chunks = chunker.chunk(policy)

    assert len(chunks) == 1
    assert "Real content." in chunks[0].text


def test_chunk_indexes_are_sequential():
    chunker = PolicyChunker()
    policy = make_policy(
        [
            {"heading": "A", "text": "First."},
            {"heading": "B", "text": "Second."},
            {"heading": "C", "text": "Third."},
        ]
    )

    chunks = chunker.chunk(policy)

    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_chunk_ids_are_deterministic():
    """Same input → same chunk ids."""
    chunker = PolicyChunker()
    policy = make_policy([{"heading": "A", "text": "Content."}])

    first = chunker.chunk(policy)
    second = chunker.chunk(policy)

    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_chunk_content_hash_is_stable():
    chunker = PolicyChunker()
    policy = make_policy([{"heading": "A", "text": "Content."}])

    first = chunker.chunk(policy)
    second = chunker.chunk(policy)

    assert first[0].content_hash == second[0].content_hash


def test_token_estimate_is_positive():
    chunker = PolicyChunker()
    policy = make_policy([{"heading": "A", "text": "Some real content here."}])

    chunks = chunker.chunk(policy)

    assert chunks[0].token_estimate > 0


# ────────────────────────────────────────────────────────────────────────
# Splitting oversized sections
# ────────────────────────────────────────────────────────────────────────


def test_oversized_section_is_split():
    chunker = PolicyChunker(max_characters=200, overlap_characters=40)

    long_text = "Sentence one. " * 50  # ~700 chars
    policy = make_policy([{"heading": "Long", "text": long_text}])

    chunks = chunker.chunk(policy)

    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 220


def test_split_prefers_sentence_break():
    """
    The chunker should cut at a sentence break rather than mid-word.

    Note: `normalize_text` collapses `\\n\\n` into spaces, so paragraph
    breaks are destroyed before the chunker sees the text. Sentence
    breaks (". ") are the reliable boundary.
    """
    chunker = PolicyChunker(max_characters=100, overlap_characters=10)

    text = "Sentence one ends here. " + ("A " * 60) + "Final sentence."
    policy = make_policy([{"heading": "H", "text": text}])

    chunks = chunker.chunk(policy)

    assert len(chunks) >= 2
    assert "Sentence one ends here." in chunks[0].text


def test_chunker_rejects_invalid_overlap():
    """max_characters must exceed overlap_characters."""
    with pytest.raises(ValueError):
        PolicyChunker(max_characters=100, overlap_characters=200)


def test_chunks_are_immutable():
    """PolicyChunkData is frozen — mutation should fail."""
    chunker = PolicyChunker()
    policy = make_policy([{"heading": "A", "text": "Content."}])

    chunks = chunker.chunk(policy)

    with pytest.raises(FrozenInstanceError):
        chunks[0].text = "mutated"  # type: ignore[misc]
