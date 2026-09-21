"""Input and output validation filters for the RAG pipeline.

These filters are defense-in-depth. They catch obvious attacks before
they reach the LLM, and prevent obvious leaks from reaching the user.
They are NOT a substitute for prompt engineering or response validation.

Design principles:
  - Prefer false positives over false negatives (better to block a
    legitimate query than let an injection through).
  - Log every block with the pattern that triggered it.
  - Feature-flagged: ``settings.input_validation_enabled``.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt injection patterns
# ---------------------------------------------------------------------------

# Each pattern is a regex. Case-insensitive. Word boundaries used where
# appropriate. These target common "jailbreak" phrasings.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\bignore\s+(all\s+)?(previous|prior|above)\s+"
        r"(instructions?|prompts?|rules?)\b",
        re.I,
    ),
    re.compile(
        r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+"
        r"(instructions?|prompts?|rules?)\b",
        re.I,
    ),
    re.compile(
        r"\bforget\s+(all\s+)?(previous|prior|above)\s+"
        r"(instructions?|prompts?|rules?)\b",
        re.I,
    ),
    re.compile(r"\boverride\s+(the\s+)?system\s+prompt\b", re.I),
    re.compile(r"\byou\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"\bact\s+as\s+(if|though)\s+you\s+(are|were)\b", re.I),
    re.compile(r"\bnew\s+instructions?\s*:", re.I),
    re.compile(r"\bsystem\s*:\s*", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"\b(jailbreak|DAN\s+mode)\b", re.I),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", re.I),
    re.compile(r"\bprint\s+(your\s+)?(system\s+)?prompt\b", re.I),
    re.compile(r"\breveal\s+(your\s+)?(system\s+)?prompt\b", re.I),
    re.compile(r"\bshow\s+me\s+(your\s+)?(system\s+)?prompt\b", re.I),
]


# ---------------------------------------------------------------------------
# XSS patterns
# ---------------------------------------------------------------------------

_XSS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<\s*script\b", re.I),
    re.compile(r"<\s*/\s*script\s*>", re.I),
    re.compile(r"<\s*iframe\b", re.I),
    re.compile(r"<\s*object\b", re.I),
    re.compile(r"<\s*embed\b", re.I),
    re.compile(r"<\s*svg\b.*?\bon\w+\s*=", re.I | re.S),
    re.compile(
        r"\bon\w+\s*=\s*[\"'][^\"']*[\"']", re.I
    ),  # onclick="...", onerror="..."
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"data\s*:\s*text/html", re.I),
]


# ---------------------------------------------------------------------------
# Sensitive data patterns (for output filtering)
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),  # OpenAI-style keys
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),  # Google API keys
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),  # Hugging Face tokens
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),  # GitHub tokens
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"),  # Bearer tokens
    re.compile(r"\bpassword\s*[:=]\s*\S+", re.I),  # password=...
    re.compile(r"\bapi[_\s-]?key\s*[:=]\s*\S+", re.I),  # api_key=...
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class ValidationResult:
    """Result of a validation check."""

    __slots__ = ("ok", "reason", "cleaned")

    def __init__(self, ok: bool, reason: str = "", cleaned: str = "") -> None:
        self.ok = ok
        self.reason = reason
        self.cleaned = cleaned

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return f"ValidationResult(ok={self.ok}, reason={self.reason!r})"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def validate_input(query: str) -> ValidationResult:
    """
    Validate a user-supplied query.

    Checks for prompt injection and XSS patterns. Returns a
    ValidationResult whose ``ok`` is True when the query is safe.
    """
    if not query or not query.strip():
        return ValidationResult(False, "Query cannot be empty.")

    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(query)
        if match:
            logger.warning(
                "Prompt injection blocked | pattern=%r | text=%r",
                match.group(0),
                query[:80],
            )
            return ValidationResult(
                False,
                "Your message contains a pattern that is not allowed.",
            )

    for pattern in _XSS_PATTERNS:
        match = pattern.search(query)
        if match:
            logger.warning(
                "XSS pattern blocked | pattern=%r | text=%r",
                match.group(0),
                query[:80],
            )
            return ValidationResult(
                False,
                "Your message contains characters that are not allowed.",
            )

    return ValidationResult(True, cleaned=query.strip())


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------


def validate_output(text: str) -> ValidationResult:
    """
    Validate an LLM-generated answer before returning it to the user.

    Checks for leaked secrets and obvious XSS payloads. Unlike input
    validation, this does NOT block the answer — it replaces the
    sensitive substring with a redaction marker and continues.

    Returns a ValidationResult whose ``cleaned`` is the sanitized text.
    """
    if not text:
        return ValidationResult(True, cleaned="")

    cleaned = text
    redactions = 0

    for pattern in _SENSITIVE_PATTERNS:
        cleaned, count = pattern.subn("[REDACTED]", cleaned)
        redactions += count

    for pattern in _XSS_PATTERNS:
        cleaned, count = pattern.subn("[REMOVED]", cleaned)
        redactions += count

    if redactions > 0:
        logger.warning(
            "Output contained %d sensitive/XSS match(es); redacted.",
            redactions,
        )

    return ValidationResult(True, cleaned=cleaned)
