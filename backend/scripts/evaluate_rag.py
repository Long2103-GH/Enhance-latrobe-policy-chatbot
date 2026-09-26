"""Evaluation of the RAG pipeline.

Runs a fixed evaluation set through the full pipeline and reports:
- Retrieval recall@k (against ground-truth chunk IDs, using the full
  retrieved pool — not just the cited subset)
- Citation validity rate
- Grounding rate
- Average confidence
- Latency percentiles
- Failure breakdown

Usage:
    python -m scripts.evaluate_rag
    python -m scripts.evaluate_rag --dataset path/to/questions.json
    python -m scripts.evaluate_rag --output reports/eval.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.core_logging import configure_logging
from app.core.security import hash_password
from app.db.database import AsyncSessionLocal, init_database
from app.db.models import User
from app.services.audit_service import AuditService
from app.services.embedding_service import EmbeddingService
from app.services.generation_service import GenerationService
from app.services.lexical_store import LexicalStore
from app.services.query_rewriter import QueryRewriterService
from app.services.rag_service import RAGService
from app.services.reranking_service import RerankingService
from app.services.retrieval_service import RetrievalService
from app.services.validation_service import ValidationService
from app.services.vector_store import VectorStore

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = BASE_DIR / "data" / "evaluation" / "questions.json"
DEFAULT_OUTPUT = BASE_DIR / "reports" / "rag_evaluation.json"


# The evaluation user is a real row in the DB so FK constraints on
# audit_events.user_id and conversations.user_id succeed.
EVAL_USER_EMAIL = "eval-harness@internal.test"
EVAL_USER_PASSWORD = "EvalHarnessPass123!"


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class QuestionResult:
    """Result for a single evaluation question."""

    question_id: str
    query: str
    expected_chunk_ids: list[str]

    retrieved_chunk_ids: list[str]
    retrieved_policy_ids: list[str]

    recall_at_k: float

    answer: str
    citations: list[str]
    grounded: bool
    confidence: float
    escalation_required: bool

    latency_ms: float
    error: str | None = None


@dataclass(slots=True)
class EvaluationReport:
    """Aggregate report over the evaluation set."""

    dataset_path: str
    started_at: str
    finished_at: str
    total_questions: int

    mean_recall_at_k: float
    median_recall_at_k: float

    citation_validity_rate: float
    grounding_rate: float
    mean_confidence: float
    escalation_rate: float

    mean_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float

    error_count: int
    failures: list[dict] = field(default_factory=list)
    per_question: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------
def load_dataset(path: Path) -> list[dict]:
    """
    Load the evaluation dataset.

    Expected format: list of
        {"id": str, "query": str, "expected_chunk_ids": [str, ...]}.
    """
    if not path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Evaluation dataset must be a JSON array.")

    return data


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def compute_recall_at_k(
    retrieved_ids: list[str],
    expected_ids: list[str],
) -> float:
    """Recall@k over chunk IDs."""
    if not expected_ids:
        return float("nan")

    expected = set(expected_ids)
    retrieved = set(retrieved_ids)

    hits = len(expected & retrieved)
    return hits / len(expected)


def safe_mean(values: list[float]) -> float:
    """Mean ignoring NaN values (NaN != NaN)."""
    cleaned = [v for v in values if v == v]
    if not cleaned:
        return 0.0
    return statistics.mean(cleaned)


def percentile(values: list[float], p: float) -> float:
    """Percentile with linear interpolation. `p` in [0, 100]."""
    if not values:
        return 0.0

    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (p / 100.0)
    lower = int(k)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = k - lower

    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


# ---------------------------------------------------------------------------
# Pipeline construction
# ---------------------------------------------------------------------------
def build_services() -> tuple[RAGService, RetrievalService]:
    """Build RAG + retrieval services for offline evaluation."""
    settings = get_settings()

    embedding_service = EmbeddingService()
    vector_store = VectorStore()
    lexical_store = LexicalStore()
    generation_service = GenerationService()
    reranking_service = RerankingService(
        bm25_weight=settings.reranking_bm25_weight,
    )
    query_rewriter = QueryRewriterService(generation_service=generation_service)

    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        lexical_store=lexical_store,
        reranking_service=reranking_service,
        query_rewriter=query_rewriter,
    )

    validation_service = ValidationService()
    audit_service = AuditService()

    rag = RAGService(
        retrieval_service=retrieval_service,
        generation_service=generation_service,
        validation_service=validation_service,
        audit_service=audit_service,
        query_rewriter=query_rewriter,
    )

    return rag, retrieval_service


# ---------------------------------------------------------------------------
# Evaluation user
# ---------------------------------------------------------------------------
async def ensure_eval_user() -> int:
    """
    Ensure an evaluation user exists in the DB and return its id.

    FK constraints require the row to exist before audit / conversation
    writes can reference it.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == EVAL_USER_EMAIL)
        )
        user = result.scalar_one_or_none()

        if user is not None:
            return user.id

        user = User(
            email=EVAL_USER_EMAIL,
            full_name="Evaluation Harness",
            password_hash=hash_password(EVAL_USER_PASSWORD),
            role="student",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
async def evaluate_one(
    rag: RAGService,
    retrieval: RetrievalService,
    item: dict,
    eval_user_id: int,
) -> QuestionResult:
    """Run a single evaluation question through the pipeline."""
    question_id = str(item.get("id", ""))
    query = str(item.get("query", "")).strip()
    expected = list(item.get("expected_chunk_ids", []))

    started = time.perf_counter()

    try:
        # Stage 1: retrieval-only (for recall@k)
        async with AsyncSessionLocal() as session:
            retrieved = await retrieval.retrieve(session, query)

        retrieved_chunk_ids = [r.chunk_id for r in retrieved]
        retrieved_policy_ids = [r.policy_id for r in retrieved]

        recall = compute_recall_at_k(retrieved_chunk_ids, expected)

        # Stage 2: full RAG answer (for grounding/citation metrics)
        async with AsyncSessionLocal() as session:
            response = await rag.answer(
                session,
                query=query,
                conversation=[],
                user_id=eval_user_id,
                request_id=f"eval-{question_id}",
            )

        latency_ms = (time.perf_counter() - started) * 1000
        citation_ids = [c.citation_id for c in response.citations]

        return QuestionResult(
            question_id=question_id,
            query=query,
            expected_chunk_ids=expected,
            retrieved_chunk_ids=retrieved_chunk_ids,
            retrieved_policy_ids=retrieved_policy_ids,
            recall_at_k=recall,
            answer=response.answer,
            citations=citation_ids,
            grounded=response.grounded,
            confidence=response.confidence,
            escalation_required=response.escalation_required,
            latency_ms=latency_ms,
        )

    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return QuestionResult(
            question_id=question_id,
            query=query,
            expected_chunk_ids=expected,
            retrieved_chunk_ids=[],
            retrieved_policy_ids=[],
            recall_at_k=float("nan"),
            answer="",
            citations=[],
            grounded=False,
            confidence=0.0,
            escalation_required=True,
            latency_ms=latency_ms,
            error=str(exc),
        )


async def run_evaluation(dataset_path: Path) -> EvaluationReport:
    """Run the full evaluation and return a report."""
    dataset = load_dataset(dataset_path)

    await init_database()
    eval_user_id = await ensure_eval_user()

    rag, retrieval = build_services()

    started_at = datetime.now(UTC).isoformat()

    results: list[QuestionResult] = []
    for item in dataset:
        result = await evaluate_one(rag, retrieval, item, eval_user_id)
        results.append(result)
        status = "ERROR" if result.error else "OK"
        print(f"[{status}] {result.question_id}: {result.query[:60]}")

    finished_at = datetime.now(UTC).isoformat()

    recalls = [r.recall_at_k for r in results]
    latencies = [r.latency_ms for r in results]
    confidences = [r.confidence for r in results if not r.error]

    total = len(results)
    grounded_count = sum(1 for r in results if r.grounded)
    escalated_count = sum(1 for r in results if r.escalation_required)
    error_count = sum(1 for r in results if r.error)
    citation_valid_count = sum(1 for r in results if r.citations)

    valid_recalls = [v for v in recalls if v == v]  # filter NaN

    return EvaluationReport(
        dataset_path=str(dataset_path),
        started_at=started_at,
        finished_at=finished_at,
        total_questions=total,
        mean_recall_at_k=safe_mean(recalls),
        median_recall_at_k=(statistics.median(valid_recalls) if valid_recalls else 0.0),
        citation_validity_rate=(citation_valid_count / total) if total else 0.0,
        grounding_rate=(grounded_count / total) if total else 0.0,
        mean_confidence=safe_mean(confidences),
        escalation_rate=(escalated_count / total) if total else 0.0,
        mean_latency_ms=safe_mean(latencies),
        p50_latency_ms=percentile(latencies, 50),
        p95_latency_ms=percentile(latencies, 95),
        error_count=error_count,
        failures=[
            {"id": r.question_id, "query": r.query, "error": r.error}
            for r in results
            if r.error
        ],
        per_question=[asdict(r) for r in results],
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_report(report: EvaluationReport, output_path: Path) -> None:
    """Write the report to JSON and print a human summary."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("RAG EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Questions:            {report.total_questions}")
    print(f"Mean Recall@k:        {report.mean_recall_at_k:.3f}")
    print(f"Median Recall@k:      {report.median_recall_at_k:.3f}")
    print(f"Citation validity:    {report.citation_validity_rate:.2%}")
    print(f"Grounding rate:       {report.grounding_rate:.2%}")
    print(f"Mean confidence:      {report.mean_confidence:.3f}")
    print(f"Escalation rate:      {report.escalation_rate:.2%}")
    print(f"Mean latency (ms):    {report.mean_latency_ms:.1f}")
    print(f"p50 latency (ms):     {report.p50_latency_ms:.1f}")
    print(f"p95 latency (ms):     {report.p95_latency_ms:.1f}")
    print(f"Errors:               {report.error_count}")
    print(f"\nReport written to:    {output_path}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the RAG pipeline against a ground-truth set."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to evaluation questions JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the JSON report",
    )
    return parser.parse_args()


async def main() -> None:
    configure_logging()
    args = parse_args()

    report = await run_evaluation(args.dataset)
    write_report(report, args.output)


if __name__ == "__main__":
    asyncio.run(main())
