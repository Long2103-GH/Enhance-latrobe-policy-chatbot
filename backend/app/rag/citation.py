"""Citation validation and grounding utilities."""

import re

from app.rag.models import RetrievalResult

# Matches citation IDs of the form [C1], [C10], [C99], etc.
# Case-sensitive: the prompt instructs the LLM to emit uppercase C.
# Does not match the comma-separated form [C1, C2] — the prompt
# requires adjacent citations ([C1][C2]).
_CITATION_PATTERN = re.compile(r"\[(C\d+)\]")


def extract_citation_ids(answer: str) -> list[str]:
    """Extract citation identifiers from an answer, preserving order."""
    return list(dict.fromkeys(_CITATION_PATTERN.findall(answer)))


def validate_citations(
    answer: str,
    retrieved: list[RetrievalResult],
) -> tuple[bool, list[str]]:
    """
    Ensure every citation in the generated answer refers to retrieved evidence.

    Returns:
        (is_valid, citation_ids). ``citation_ids`` preserves answer order
        and is populated even when validation fails, so callers can report
        which IDs were cited.
    """
    citation_ids = extract_citation_ids(answer)

    valid_ids = {f"C{index + 1}" for index in range(len(retrieved))}

    if not citation_ids:
        return False, []

    if not set(citation_ids).issubset(valid_ids):
        return False, citation_ids

    return True, citation_ids
