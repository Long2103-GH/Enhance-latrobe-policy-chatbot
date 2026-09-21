"""Reranking service for retrieved policy chunks.

Provides a second-stage ranking over a candidate pool produced by
hybrid retrieval. Reranking improves precision by applying a
higher-quality (but slower) scoring model to a small set of candidates.
"""

import logging
from collections.abc import Sequence
from typing import Any

from rank_bm25 import BM25Okapi

from app.core.config import get_settings
from app.rag.models import RetrievalResult
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)


class RerankingService:
    """
    Rerank retrieved chunks using BM25 over chunk text.

    Reranking is applied AFTER hybrid fusion. It re-scores the fused
    candidates so that chunks most lexically aligned with the query
    rise to the top.

    Design notes:
      - BM25 is fast, deterministic, and requires no model weights.
      - A cross-encoder can be plugged in later without changing the
        service interface.
      - Score blending: ``bm25_weight`` controls the mix between the
        fused score and the BM25 score.
    """

    def __init__(self, bm25_weight: float = 0.4) -> None:
        if not 0.0 <= bm25_weight <= 1.0:
            raise ValueError("bm25_weight must be between 0.0 and 1.0.")

        self.settings = get_settings()
        self.bm25_weight = bm25_weight

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalResult],
        *,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """
        Rerank candidates by blending fused score with BM25 score.

        Returns a new list of RetrievalResult, sorted by rerank_score desc.
        """
        if not candidates:
            return []

        query_tokens = self._tokenize(query)

        if not query_tokens:
            return list(candidates[: top_k or len(candidates)])

        corpus_tokens = [self._tokenize(result.text) or [""] for result in candidates]

        bm25 = BM25Okapi(corpus_tokens)
        raw_scores = bm25.get_scores(query_tokens)
        normalized = self._min_max_normalize(raw_scores)

        reranked: list[RetrievalResult] = []

        for result, bm25_score in zip(candidates, normalized):
            blended = (
                1.0 - self.bm25_weight
            ) * result.fused_score + self.bm25_weight * bm25_score

            reranked.append(
                RetrievalResult(
                    chunk_id=result.chunk_id,
                    policy_id=result.policy_id,
                    title=result.title,
                    section=result.section,
                    text=result.text,
                    url=result.url,
                    vector_score=result.vector_score,
                    lexical_score=result.lexical_score,
                    fused_score=result.fused_score,
                    rerank_score=blended,
                )
            )

        reranked.sort(key=lambda item: item.rerank_score, reverse=True)

        limit = top_k or self.settings.final_context_chunks
        return reranked[:limit]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Lowercase + split on whitespace after normalization."""
        if not text:
            return []

        normalized = normalize_text(text).lower()
        return [token for token in normalized.split(" ") if token]

    @staticmethod
    def _min_max_normalize(values: Sequence[float] | Any) -> list[float]:
        """
        Scale values into [0, 1] using min-max normalization.

        Accepts lists, tuples, or numpy arrays. Returns a plain Python list.
        """
        try:
            values = list(values)
        except TypeError:
            return []

        if len(values) == 0:
            return []

        low = float(min(values))
        high = float(max(values))

        if abs(high - low) < 1e-9:
            # All scores are effectively equal.
            return [1.0] * len(values)

        return [float((v - low) / (high - low)) for v in values]
