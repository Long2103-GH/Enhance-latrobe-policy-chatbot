"""Create the application database schema."""

import asyncio
import logging
import sys

from app.core.core_logging import configure_logging
from app.core.dirs import ensure_runtime_directories
from app.db.database import init_database

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging()
    ensure_runtime_directories()
    logger.info("Initializing database...")
    await init_database()
    logger.info("Database initialized successfully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        logger.exception("Database initialization failed.")
        sys.exit(1)
