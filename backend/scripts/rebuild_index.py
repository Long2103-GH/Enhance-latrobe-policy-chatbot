"""Rebuild the SQLite FTS5 lexical index.

This script rebuilds ONLY the lexical (SQLite FTS5) index from the
existing ``policy_chunks`` table. It does not re-embed vectors or
re-populate Qdrant — use ``scripts.ingest_policies`` for a full
re-ingestion.
"""

import asyncio

from app.db.database import AsyncSessionLocal, init_database
from app.services.lexical_store import LexicalStore


async def main() -> None:
    """Rebuild SQLite lexical retrieval index."""
    await init_database()

    async with AsyncSessionLocal() as session:
        await LexicalStore().rebuild(session)

    print("Lexical retrieval index rebuilt.")


if __name__ == "__main__":
    asyncio.run(main())
