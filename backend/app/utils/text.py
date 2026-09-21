"""Text processing utilities."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Collapse whitespace and strip leading/trailing characters."""
    if not isinstance(text, str):
        raise TypeError("Expected string input for text normalization.")

    text = text.replace("\x00", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def estimate_tokens(text: str) -> int:
    """
    Estimate token count from character length.

    Uses a 4-chars-per-token heuristic — sufficient for controlling
    context size without coupling ingestion to a specific tokenizer.
    """
    if not isinstance(text, str):
        raise TypeError("Expected string input for token estimation.")

    if not text:
        return 0

    return max(1, len(text) // 4)
