"""Export seeded test credentials to a CSV file.

SECURITY WARNING
----------------
This script writes PLAINTEXT passwords to disk. It is intended ONLY
for local development and manual testing.

Safety features:
  - Refuses to run when APP_ENV=production (unless --force).
  - Refuses to write outside the data/test_artifacts/ folder.
  - Sets file permissions to 0600 (owner read/write only) on POSIX.
  - Prints a warning reminding you not to commit the file.

Usage:
    python -m scripts.export_test_credentials
    python -m scripts.export_test_credentials --force
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.core_logging import configure_logging
from app.db.database import AsyncSessionLocal
from app.db.models import User

logger = logging.getLogger(__name__)


# Path is fixed and confined to a gitignored folder.
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "test_artifacts"
OUTPUT_FILE = OUTPUT_DIR / "seed_credentials.csv"


def _password_for(full_name: str) -> str:
    """Reproduce the seed script's password rule."""
    parts = full_name.split()
    if not parts:
        return "UnknownX@LTU2026"
    return f"{parts[0]}{parts[-1][0]}@LTU2026"


def _harden_file_permissions(path: Path) -> None:
    """Best-effort: chmod 600 on POSIX. No-op on Windows."""
    try:
        os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


async def export(*, force: bool = False) -> int:
    """Export all seeded users to a CSV. Returns row count."""
    settings = get_settings()

    if settings.app_env.lower() == "production" and not force:
        raise RuntimeError(
            "Refusing to export credentials while APP_ENV=production. "
            "Use --force only if you truly intend to."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).order_by(User.role, User.id))
        users = result.scalars().all()

    if not users:
        print("No users found in the database. Run the seed script first.")
        return 0

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["institutional_id", "email", "role", "full_name", "password"])
        for user in users:
            writer.writerow(
                [
                    user.institutional_id or "",
                    user.email,
                    user.role,
                    user.full_name,
                    _password_for(user.full_name),
                ]
            )

    _harden_file_permissions(OUTPUT_FILE)
    return len(users)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export seeded test credentials to CSV."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow running even when APP_ENV=production.",
    )
    return parser.parse_args()


async def main() -> None:
    configure_logging()
    args = _parse_args()

    settings = get_settings()
    if settings.app_env.lower() == "production" and not args.force:
        print(
            "Refusing to run in production. "
            "Set APP_ENV=development, or pass --force (not recommended)."
        )
        sys.exit(1)

    count = await export(force=args.force)

    if count == 0:
        return

    print()
    print("=" * 60)
    print(f"Exported {count} users to:")
    print(f"  {OUTPUT_FILE}")
    print("=" * 60)
    print()
    print("SECURITY REMINDERS:")
    print("  - This file contains PLAINTEXT passwords.")
    print("  - It is gitignored. Do NOT remove that rule.")
    print("  - Do NOT share this file outside your team.")
    print("  - Delete it once testing is done.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
