"""Citation extraction and validation tests."""

import pytest

from app.rag.citation import extract_citation_ids, validate_citations
from app.rag.models import RetrievalResult


def make_result(chunk_id: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        policy_id="p1",
        title="T",
        section="S",
        text="t",
        url="https://example.test",
        vector_score=0.9,
        lexical_score=0.0,
        fused_score=0.0,
    )


@pytest.fixture
def eight_results():
    return [make_result(f"chunk-{i}") for i in range(8)]


# ────────────────────────────────────────────────────────────────────────
# extract_citation_ids
# ────────────────────────────────────────────────────────────────────────


def test_extract_finds_single_citation():
    assert extract_citation_ids("See [C1].") == ["C1"]


def test_extract_finds_multiple_citations():
    assert extract_citation_ids("See [C1] and [C2].") == ["C1", "C2"]


def test_extract_deduplicates_preserving_order():
    assert extract_citation_ids("[C1] [C2] [C1] [C3] [C2]") == ["C1", "C2", "C3"]


def test_extract_ignores_lowercase():
    assert extract_citation_ids("[c1]") == []


def test_extract_ignores_no_digits():
    assert extract_citation_ids("[C]") == []


def test_extract_handles_multi_digit():
    assert extract_citation_ids("[C10] [C99]") == ["C10", "C99"]


def test_extract_empty_answer():
    assert extract_citation_ids("") == []


def test_extract_no_citations():
    assert extract_citation_ids("Just an answer with no sources.") == []


# ────────────────────────────────────────────────────────────────────────
# validate_citations
# ────────────────────────────────────────────────────────────────────────


def test_validate_all_valid_citations(eight_results):
    valid, ids = validate_citations("Fact [C1]. Another [C3].", eight_results)

    assert valid is True
    assert ids == ["C1", "C3"]


def test_validate_out_of_range_citation(eight_results):
    valid, ids = validate_citations("Fact [C99].", eight_results)

    assert valid is False
    assert "C99" in ids


def test_validate_empty_answer_returns_invalid(eight_results):
    valid, ids = validate_citations("No citations here.", eight_results)

    assert valid is False
    assert ids == []


def test_validate_no_retrieved_chunks():
    valid, ids = validate_citations("Fact [C1].", [])

    assert valid is False


def test_validate_partial_invalid(eight_results):
    """One valid + one invalid → invalid overall."""
    valid, ids = validate_citations("A [C1]. B [C50].", eight_results)

    assert valid is False
    assert set(ids) == {"C1", "C50"}


def test_validate_duplicates_are_accepted(eight_results):
    """Same citation twice is still valid."""
    valid, ids = validate_citations("[C1] [C1] [C2]", eight_results)

    assert valid is True
    assert ids == ["C1", "C2"]
