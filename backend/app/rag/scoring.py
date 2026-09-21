"""Hybrid retrieval scoring."""

from collections.abc import Sequence

from app.rag.models import RetrievalResult


def reciprocal_rank_fusion(
    vector_results: Sequence[RetrievalResult],
    lexical_results: Sequence[RetrievalResult],
    *,
    k: int = 60,
) -> list[RetrievalResult]:
    """
    Combine vector and lexical rankings using Reciprocal Rank Fusion.

    NOTE: This function mutates the ``fused_score`` (and, on collision,
    ``lexical_score``) of the ``RetrievalResult`` objects it receives.
    Callers must pass freshly constructed objects that are not shared
    across calls — the vector and lexical stores already do this.

    The returned list is sorted by descending fused score.
    """
    by_chunk: dict[str, RetrievalResult] = {}

    for rank, result in enumerate(vector_results, start=1):
        by_chunk[result.chunk_id] = result
        result.fused_score += 1.0 / (k + rank)

    for rank, result in enumerate(lexical_results, start=1):
        existing = by_chunk.get(result.chunk_id)

        if existing is None:
            by_chunk[result.chunk_id] = result
            existing = result
        else:
            existing.lexical_score = result.lexical_score

        existing.fused_score += 1.0 / (k + rank)

    return sorted(
        by_chunk.values(),
        key=lambda item: item.fused_score,
        reverse=True,
    )
