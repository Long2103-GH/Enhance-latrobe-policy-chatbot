"""Retrieval pipeline + Reciprocal Rank Fusion tests."""

import pytest

from app.rag.models import RetrievalResult
from app.rag.scoring import reciprocal_rank_fusion


def make_result(
    chunk_id: str,
    vector: float = 0.0,
    lexical: float = 0.0,
    fused: float = 0.0,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        policy_id="p1",
        title="T",
        section="S",
        text="t",
        url="https://example.test",
        vector_score=vector,
        lexical_score=lexical,
        fused_score=fused,
    )


# ────────────────────────────────────────────────────────────────────────
# reciprocal_rank_fusion
# ────────────────────────────────────────────────────────────────────────


def test_rrf_prefers_chunk_in_both_lists():
    """A chunk appearing in both lists ranks above one in only one list."""
    vector_results = [make_result("A"), make_result("B")]
    lexical_results = [make_result("B"), make_result("C")]

    fused = reciprocal_rank_fusion(vector_results, lexical_results, k=60)

    chunk_ids = [r.chunk_id for r in fused]
    assert chunk_ids[0] == "B"


def test_rrf_preserves_all_unique_chunks():
    vector_results = [make_result("A"), make_result("B")]
    lexical_results = [make_result("B"), make_result("C")]

    fused = reciprocal_rank_fusion(vector_results, lexical_results, k=60)

    assert {r.chunk_id for r in fused} == {"A", "B", "C"}


def test_rrf_handles_empty_vector_results():
    lexical_results = [make_result("A"), make_result("B")]

    fused = reciprocal_rank_fusion([], lexical_results, k=60)

    assert [r.chunk_id for r in fused] == ["A", "B"]


def test_rrf_handles_empty_lexical_results():
    vector_results = [make_result("A"), make_result("B")]

    fused = reciprocal_rank_fusion(vector_results, [], k=60)

    assert [r.chunk_id for r in fused] == ["A", "B"]


def test_rrf_handles_both_empty():
    fused = reciprocal_rank_fusion([], [], k=60)

    assert fused == []


def test_rrf_scores_are_monotonically_decreasing():
    vector_results = [make_result("A"), make_result("B"), make_result("C")]
    lexical_results = []

    fused = reciprocal_rank_fusion(vector_results, lexical_results, k=60)

    scores = [r.fused_score for r in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_k_parameter_affects_scoring():
    """
    A larger k reduces the difference between adjacent ranks.

    Math: 1/(k+1) - 1/(k+2). As k grows, this difference shrinks.
    RRF mutates ``fused_score`` in place, so we build fresh result
    objects for each call.
    """
    small_vector = [make_result("A"), make_result("B")]
    small_k = reciprocal_rank_fusion(small_vector, [], k=1)

    large_vector = [make_result("A"), make_result("B")]
    large_k = reciprocal_rank_fusion(large_vector, [], k=1000)

    small_gap = small_k[0].fused_score - small_k[1].fused_score
    large_gap = large_k[0].fused_score - large_k[1].fused_score

    assert small_gap > large_gap


# ────────────────────────────────────────────────────────────────────────
# RetrievalService (integration with mocked stores)
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retrieval_service_returns_fused_results(
    db_session,
    mock_embedding_service,
    mock_vector_store,
    mock_lexical_store,
):
    """RetrievalService merges vector + lexical results."""
    from app.services.embedding_service import EmbeddingService
    from app.services.lexical_store import LexicalStore
    from app.services.retrieval_service import RetrievalService
    from app.services.vector_store import VectorStore

    mock_vector_store["v1"] = {
        "vector": [0.1] * 1024,
        "payload": {
            "chunk_id": "v1",
            "policy_id": "p1",
            "title": "Vector Only",
            "url": "https://example.test/1",
            "section": "S",
            "text": "vector text",
            "chunk_index": 0,
        },
    }
    mock_lexical_store.append(
        {
            "chunk_id": "l1",
            "policy_id": "p1",
            "title": "Lexical Only",
            "section": "S",
            "text": "lexical text",
            "url": "https://example.test/2",
        }
    )

    service = RetrievalService(
        embedding_service=EmbeddingService(),
        vector_store=VectorStore(),
        lexical_store=LexicalStore(),
    )

    results = await service.retrieve(db_session, "text")

    chunk_ids = {r.chunk_id for r in results}
    assert "v1" in chunk_ids
    assert "l1" in chunk_ids
