"""Run policy ingestion."""

import asyncio

from app.core.core_logging import configure_logging
from app.db.database import AsyncSessionLocal, init_database
from app.services.ingestion_service import IngestionService


async def main() -> None:
    """Run complete policy ingestion."""
    configure_logging()

    await init_database()

    async with AsyncSessionLocal() as session:
        service = IngestionService()
        result = await service.ingest(session)

        print(
            f"Ingestion complete: "
            f"{result['policies']} policies, "
            f"{result['chunks']} chunks."
        )


if __name__ == "__main__":
    asyncio.run(main())
