"""Hybrid policy retrieval service with broad candidate fusion.

Two-pass retrieval:

  1. First pass — hybrid semantic + lexical, RRF-fused over a broad
     candidate pool. Fast; runs on every request.

  2. Broadening pass — only if the first pass produced a very low top
     fused score. Asks the query rewriter for a broader phrase, then
     re-runs hybrid retrieval. The broadened results are used as the
     primary source because the original query is known to have failed.

Final selection applies three policies:

  - Per-policy cap: at most ``max_chunks_per_policy`` chunks from any
    single policy.

  - Deduplication: near-duplicate chunks (same policy, same section,
    ≥60% character overlap) are collapsed to the higher-ranked one.

  - Adaptive context window: fewer chunks when retrieval confidence is
    high, more when it is low. Confidence is the top fused RRF score.
"""

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.core_logging import debug_logger
from app.rag.models import RetrievalResult
from app.rag.scoring import reciprocal_rank_fusion
from app.services.embedding_service import EmbeddingService
from app.services.lexical_store import LexicalStore
from app.services.query_rewriter import QueryRewriterService
from app.services.reranking_service import RerankingService
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)
dev_log = debug_logger(__name__)


# Character-overlap ratio above which two chunks (same policy+section)
# are considered duplicates and the lower-ranked one is dropped.
_DEDUP_OVERLAP_THRESHOLD = 0.60

# Regex used to count "content words" in a query for the adaptive window.
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class RetrievalService:
    """Perform hybrid semantic + lexical policy retrieval."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        lexical_store: LexicalStore,
        reranking_service: RerankingService | None = None,
        query_rewriter: QueryRewriterService | None = None,
    ) -> None:
        self.settings = get_settings()
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.lexical_store = lexical_store
        self.reranking_service = reranking_service
        self.query_rewriter = query_rewriter

    async def retrieve(
        self,
        session: AsyncSession,
        query: str,
    ) -> list[RetrievalResult]:
        """Retrieve and fuse policy evidence, with optional broadening."""
        first_pass = await self._hybrid_retrieve(session, query)

        top_score = first_pass[0].fused_score if first_pass else 0.0

        dev_log.warning(
            "RETRIEVAL FIRST PASS | n=%d | top_score=%s",
            len(first_pass),
            top_score,
        )

        broadened_results: list[RetrievalResult] = []
        broadened_used = False

        if (
            self.query_rewriter is not None
            and self.settings.query_broadening_enabled
            and top_score < self.settings.retrieval_low_confidence_threshold
        ):
            dev_log.warning(
                "RETRIEVAL LOW CONFIDENCE (%.4f < %.4f) — broadening query.",
                top_score,
                self.settings.retrieval_low_confidence_threshold,
            )

            broadened_query = await self.query_rewriter.broaden(query)

            if broadened_query and broadened_query != query:
                broadened_results = await self._hybrid_retrieve(
                    session, broadened_query
                )
                broadened_used = True

                dev_log.warning(
                    "RETRIEVAL BROADENED | n=%d | top_score=%s",
                    len(broadened_results),
                    broadened_results[0].fused_score if broadened_results else None,
                )

        if broadened_used and broadened_results:
            primary = broadened_results
            secondary = first_pass
        else:
            primary = first_pass
            secondary = []

        if self.reranking_service is not None and self.settings.reranking_enabled:
            primary = self.reranking_service.rerank(query, primary)

        final = self._select_final_context(primary, secondary, top_score, query)

        dev_log.warning(
            "RETRIEVAL FINAL | n=%d | policies=%d | ids=%s",
            len(final),
            len({r.policy_id for r in final}),
            [r.chunk_id for r in final],
        )

        return final

    # ─── Hybrid retrieval core ─────────────────────────────────────
    async def _hybrid_retrieve(
        self,
        session: AsyncSession,
        query: str,
    ) -> list[RetrievalResult]:
        """One hybrid pass: embed, vector search, lexical search, RRF."""
        query_vector = await self.embedding_service.embed(query)
        candidate_limit = max(self.settings.vector_top_k, 20)

        vector_results = await self.vector_store.search(
            query_vector,
            limit=candidate_limit,
        )
        lexical_results = await self.lexical_store.search(
            session,
            query,
            limit=max(self.settings.lexical_top_k, 20),
        )

        return reciprocal_rank_fusion(
            vector_results,
            lexical_results,
            k=self.settings.rrf_k,
        )

    # ─── Adaptive window size ──────────────────────────────────────
    def _target_chunk_count(self, top_score: float, query: str) -> int:
        """
        Choose the number of context chunks based on retrieval confidence
        and the query's own self-sufficiency.

        Short, under-specified queries ("I missed my deadline") don't tell
        us what aspect the user cares about, so we send a wider window even
        when retrieval confidence is high — the extra chunks cover the
        other angles the user might need.

        Long, self-contained queries are precise, so a narrow window is safe.
        """
        if not self.settings.context_by_confidence:
            return self.settings.final_context_chunks

        # Count content words (regex strips punctuation so "deadline." counts).
        content_words = _TOKEN_RE.findall(query.lower())
        content_words = [w for w in content_words if len(w) > 2]
        is_short_query = len(content_words) < 6

        if top_score >= 0.30:
            base = 6
        elif top_score >= 0.15:
            base = 8
        elif top_score >= 0.05:
            base = self.settings.final_context_chunks
        else:
            base = min(self.settings.final_context_chunks + 2, 14)

        if is_short_query:
            base = max(base, 10)

        return base

    # ─── Final selection ───────────────────────────────────────────
    def _select_final_context(
        self,
        primary: list[RetrievalResult],
        secondary: list[RetrievalResult],
        top_score: float,
        query: str,
    ) -> list[RetrievalResult]:
        """
        Build the final context list.

        Applies:
          - deduplication (same policy + section + high overlap)
          - per-policy cap
          - adaptive target count based on confidence
          - score floor on the primary list
        """
        target = self._target_chunk_count(top_score, query)
        per_policy_cap = self.settings.max_chunks_per_policy
        score_floor = self.settings.min_retrieval_score

        selected: list[RetrievalResult] = []
        per_policy_count: dict[str, int] = {}
        seen_ids: set[str] = set()

        def _is_duplicate(candidate: RetrievalResult) -> bool:
            for existing in selected:
                if existing.policy_id != candidate.policy_id:
                    continue
                if existing.section != candidate.section:
                    continue
                if (
                    _overlap_ratio(existing.text, candidate.text)
                    >= _DEDUP_OVERLAP_THRESHOLD
                ):
                    return True
            return False

        def _try_add(result: RetrievalResult, enforce_floor: bool) -> bool:
            if result.chunk_id in seen_ids:
                return False
            if enforce_floor and result.fused_score < score_floor:
                return False
            if per_policy_count.get(result.policy_id, 0) >= per_policy_cap:
                return False
            if _is_duplicate(result):
                return False

            seen_ids.add(result.chunk_id)
            per_policy_count[result.policy_id] = (
                per_policy_count.get(result.policy_id, 0) + 1
            )
            selected.append(result)
            return True

        # Pass 1 — primary list with score floor
        for r in primary:
            if len(selected) >= target:
                break
            _try_add(r, enforce_floor=True)

        # Pass 2 — primary list without score floor
        if len(selected) < target:
            for r in primary:
                if len(selected) >= target:
                    break
                _try_add(r, enforce_floor=False)

        # Pass 3 — secondary list with score floor
        if len(selected) < target:
            for r in secondary:
                if len(selected) >= target:
                    break
                _try_add(r, enforce_floor=True)

        # Pass 4 — secondary list without score floor
        if len(selected) < target:
            for r in secondary:
                if len(selected) >= target:
                    break
                _try_add(r, enforce_floor=False)

        return selected


# ---------------------------------------------------------------------------
# Overlap helper
# ---------------------------------------------------------------------------
def _overlap_ratio(a: str, b: str) -> float:
    """
    Compute character-level overlap ratio between two strings.

    Uses a Jaccard-style comparison on 100-character shingles sampled
    every 20 characters (a performance/accuracy tradeoff — dense shingling
    would be exact but slower).
    """
    if not a or not b:
        return 0.0
    if len(a) < 100 or len(b) < 100:
        # Fall back to simple containment for short strings.
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        return 1.0 if shorter in longer else 0.0

    shingle_size = 100

    def shingles(text: str) -> set[str]:
        return {
            text[i : i + shingle_size]
            for i in range(0, len(text) - shingle_size + 1, 20)
        }

    sa = shingles(a)
    sb = shingles(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0
