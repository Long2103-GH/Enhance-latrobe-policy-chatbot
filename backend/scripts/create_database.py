"""Initialize the application database."""

import asyncio

from app.core.core_logging import configure_logging
from app.db.database import init_database


async def main() -> None:
    """Create database tables."""
    configure_logging()
    await init_database()
    print("Database initialized successfully.")


if __name__ == "__main__":
    asyncio.run(main())
