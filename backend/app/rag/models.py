"""RAG domain models."""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class PolicyChunkData:
    """Canonical chunk before persistence."""

    chunk_id: str
    policy_external_id: str
    title: str
    url: str
    section: str
    chunk_index: int
    text: str
    content_hash: str
    token_estimate: int


@dataclass(slots=True)
class RetrievalResult:
    """
    Retrieved policy chunk with ranking metadata.

    Mutable: ``fused_score`` is written in place by
    ``reciprocal_rank_fusion`` and ``rerank_score`` by the reranker.
    Callers must not share instances across retrievals.
    """

    chunk_id: str
    policy_id: str
    title: str
    section: str
    text: str
    url: str
    vector_score: float
    lexical_score: float
    fused_score: float
    rerank_score: float = 0.0