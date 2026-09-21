"""Grounding and response validation."""

from app.core.config import get_settings
from app.rag.citation import validate_citations
from app.rag.models import RetrievalResult

_DISCLAIMER = (
    "This response is based on the retrieved La Trobe University policy "
    "documents available to the system. It is not legal advice or an "
    "official determination of university policy. Where your situation "
    "requires an official interpretation or clarification, contact the "
    "relevant La Trobe University administration or policy owner."
)


class ValidationService:
    """Apply deterministic safeguards to generated answers."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def validate(
        self,
        answer: str,
        retrieved: list[RetrievalResult],
    ) -> tuple[bool, float, list[str]]:
        """Validate citation integrity and estimate grounding confidence."""
        citations_valid, citation_ids = validate_citations(answer, retrieved)

        if not citations_valid:
            return False, 0.0, citation_ids

        cited_count = len(citation_ids)

        confidence = min(
            1.0,
            0.50 + (0.10 * min(cited_count, 4)) + self._evidence_quality(retrieved),
        )

        return (
            confidence >= self.settings.min_generation_support,
            round(confidence, 3),
            citation_ids,
        )

    @staticmethod
    def _evidence_quality(retrieved: list[RetrievalResult]) -> float:
        """Estimate evidence quality from retrieval agreement."""
        if not retrieved:
            return 0.0

        top = retrieved[:3]

        vector_present = sum(1 for result in top if result.vector_score > 0)
        lexical_present = sum(1 for result in top if result.lexical_score > 0)

        agreement = (vector_present + lexical_present) / max(1, len(top) * 2)

        return min(0.25, agreement * 0.25)

    @staticmethod
    def needs_escalation(answer: str, confidence: float) -> bool:
        """Detect situations where official clarification is advisable."""
        escalation_terms = [
            "contact",
            "official clarification",
            "policy owner",
            "administration",
            "cannot determine",
            "not specified",
            "insufficient information",
        ]

        normalized = answer.lower()

        return confidence < 0.75 or any(term in normalized for term in escalation_terms)

    @staticmethod
    def disclaimer() -> str:
        """Return the mandatory policy disclaimer."""
        return _DISCLAIMER
