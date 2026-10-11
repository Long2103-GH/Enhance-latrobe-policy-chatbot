"""Runtime directory bootstrap.

Ensures the directories that the application writes to at runtime exist
before any script or the API tries to open files inside them. These
directories are gitignored, so a fresh clone legitimately doesn't have
them until something creates them. This module is that something.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings


def ensure_runtime_directories() -> None:
    """Create storage, qdrant, logs, and data subdirectories if missing."""
    settings = get_settings()

    # SQLite database parent (e.g. backend/storage/).
    db_path = Path(settings.sqlite_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Qdrant local index.
    (db_path.parent / "qdrant").mkdir(parents=True, exist_ok=True)

    # Log file parent.
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Policy data directories (safe to pre-create).
    base = db_path.parent.parent  # backend/
    (base / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (base / "data" / "evaluation").mkdir(parents=True, exist_ok=True)
