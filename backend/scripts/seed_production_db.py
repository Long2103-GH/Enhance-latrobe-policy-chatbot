"""Production-grade identity seeding script.

Generates a realistic La Trobe University user base for testing the
authentication and RAG pipeline:

  - 60 students      (email: {id}@students.latrobe.edu.au)
  - 20 faculty       (email: {id}@latrobe.edu.au)
  - 15 staff         (email: {id}@latrobe.edu.au)
  -  5 admins        (email: {id}@latrobe.edu.au)

Total: 100 users.

Default password format per user:
    {FirstName}{LastInitial}@LTU2026
    e.g. "Alex Taylor" -> "AlexT@LTU2026"

The script is:
  - Idempotent:   skips users whose email already exists.
  - Safe:         refuses to run when APP_ENV=production.
  - Deterministic: same seed data on every run.
  - Verifiable:   prints a summary at the end.

Usage:
    python -m scripts.seed_production_db
    python -m scripts.seed_production_db --force      # override production guard
    python -m scripts.seed_production_db --wipe       # delete all users first
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.core_logging import configure_logging
from app.core.security import hash_password
from app.db.database import AsyncSessionLocal, init_database
from app.db.models import User

logger = logging.getLogger(__name__)


# =============================================================================
# Name pools
# =============================================================================

FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Sam",
    "Priya",
    "Raman",
    "Sarah",
    "Michael",
    "Emily",
    "Daniel",
    "Jessica",
    "James",
    "Olivia",
    "Liam",
    "Sophia",
    "Noah",
    "Isabella",
    "William",
    "Mia",
    "Benjamin",
    "Charlotte",
    "Lucas",
    "Amelia",
    "Henry",
    "Harper",
    "Alexander",
    "Evelyn",
    "Mason",
    "Abigail",
    "Ethan",
    "Emma",
    "Logan",
    "Elizabeth",
    "Jacob",
    "Sofia",
    "Jackson",
    "Avery",
    "Sebastian",
    "Ella",
    "Aiden",
    "Scarlett",
    "Matthew",
    "Grace",
    "Samuel",
    "Chloe",
    "David",
    "Victoria",
    "Joseph",
    "Riley",
    "Carter",
    "Aria",
    "Owen",
    "Lily",
    "Wyatt",
    "Hannah",
    "John",
    "Zoey",
    "Luke",
    "Nora",
    "Julian",
    "Layla",
]

LAST_NAMES = [
    "Taylor",
    "Morgan",
    "Rivera",
    "Nguyen",
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Jackson",
    "White",
    "Harris",
    "Martin",
    "Thompson",
    "Robinson",
    "Clark",
    "Lewis",
    "Lee",
    "Walker",
    "Hall",
    "Allen",
    "Young",
    "King",
    "Wright",
    "Scott",
    "Torres",
    "Hill",
    "Flores",
    "Green",
    "Adams",
    "Nelson",
    "Baker",
    "Campbell",
    "Mitchell",
    "Carter",
    "Roberts",
]


# =============================================================================
# User specification
# =============================================================================


@dataclass(frozen=True)
class SeedSpec:
    """How many users of each role to generate."""

    role: str
    count: int
    email_domain: str


SEED_PLAN: list[SeedSpec] = [
    SeedSpec(role="student", count=60, email_domain="students.latrobe.edu.au"),
    SeedSpec(role="faculty", count=20, email_domain="latrobe.edu.au"),
    SeedSpec(role="staff", count=15, email_domain="latrobe.edu.au"),
    SeedSpec(role="admin", count=5, email_domain="latrobe.edu.au"),
]


# =============================================================================
# Helpers
# =============================================================================


def _make_password(first_name: str, last_name: str) -> str:
    """Default password: {First}{LastInitial}@LTU2026."""
    return f"{first_name}{last_name[0]}@LTU2026"


class _IdGenerator:
    """
    Produces unique 8-digit institutional IDs in [10000000, 99999999].

    Seeded so the same run always yields the same IDs. Idempotent runs
    will skip users whose email already exists, but even a fresh DB gets
    deterministic IDs.
    """

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._used: set[str] = set()

    def next(self) -> str:
        while True:
            candidate = f"{self._rng.randint(10000000, 99999999)}"
            if candidate not in self._used:
                self._used.add(candidate)
                return candidate


# =============================================================================
# Core seeding logic
# =============================================================================


async def _seed_user(
    session: AsyncSession,
    *,
    institutional_id: str,
    email: str,
    full_name: str,
    role: str,
    password: str,
) -> bool:
    """Insert one user if their email does not exist. Returns True if created."""
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        return False

    session.add(
        User(
            email=email,
            institutional_id=institutional_id,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
    )
    return True


async def _wipe_users(session: AsyncSession) -> int:
    """Delete all users. Returns the number deleted."""
    result = await session.execute(delete(User))
    return result.rowcount or 0


async def seed(*, wipe: bool = False, force: bool = False) -> dict[str, int]:
    """Run the full seeding process. Returns per-role counts."""
    settings = get_settings()

    if settings.app_env.lower() == "production" and not force:
        raise RuntimeError(
            "Refusing to seed the production database. "
            "Pass --force to override (NOT recommended)."
        )

    await init_database()

    # Deterministic RNG so IDs and names are reproducible across runs.
    rng = random.Random(20260917)
    id_gen = _IdGenerator(rng)
    counts: dict[str, int] = {}

    async with AsyncSessionLocal() as session:
        if wipe:
            removed = await _wipe_users(session)
            await session.commit()
            logger.info("Wiped %d existing users.", removed)

        for spec in SEED_PLAN:
            created = 0
            for _ in range(spec.count):
                first = rng.choice(FIRST_NAMES)
                last = rng.choice(LAST_NAMES)
                full_name = f"{first} {last}"
                institutional_id = id_gen.next()
                email = f"{institutional_id}@{spec.email_domain}"
                password = _make_password(first, last)

                inserted = await _seed_user(
                    session,
                    institutional_id=institutional_id,
                    email=email,
                    full_name=full_name,
                    role=spec.role,
                    password=password,
                )
                if inserted:
                    created += 1

            counts[spec.role] = created

        await session.commit()

    return counts


# =============================================================================
# CLI
# =============================================================================


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed a realistic La Trobe user base for testing."
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Delete all existing users before seeding.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow running even when APP_ENV=production (DANGEROUS).",
    )
    return parser.parse_args()


async def _print_sample_credentials() -> None:
    """Print one sample credential per role from the DB."""
    async with AsyncSessionLocal() as session:
        for spec in SEED_PLAN:
            result = await session.execute(
                select(User)
                .where(User.role == spec.role)
                .order_by(User.id.asc())
                .limit(1)
            )
            user = result.scalar_one_or_none()
            if user is None:
                continue
            first_name = user.full_name.split(" ")[0]
            last_name = user.full_name.split(" ")[-1]
            password = _make_password(first_name, last_name)
            print(f"  {spec.role:<10} {user.email:<40} / {password}")


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

    counts = await seed(wipe=args.wipe, force=args.force)

    total = sum(counts.values())
    print()
    print("=" * 60)
    print("SEED SUMMARY")
    print("=" * 60)
    for role in ("student", "faculty", "staff", "admin"):
        print(f"  {role:<10} created: {counts.get(role, 0):>4}")
    print("-" * 60)
    print(f"  Total new users: {total}")
    print("=" * 60)
    print()
    print("Default password format: {First}{LastInitial}@LTU2026")
    print("  e.g. 'Alex Taylor' -> 'AlexT@LTU2026'")
    print()
    print("Sample credentials (first user per role):")
    await _print_sample_credentials()


if __name__ == "__main__":
    asyncio.run(main())
