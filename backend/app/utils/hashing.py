"""Hashing utilities."""

import hashlib


def sha256_text(text: str) -> str:
    """Return the SHA-256 hexadecimal digest of ``text``."""
    if not isinstance(text, str):
        raise TypeError("Expected string input for hashing.")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
