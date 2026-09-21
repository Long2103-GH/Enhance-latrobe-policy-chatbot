"""Administrative endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.auth.base import CurrentUser
from app.db.database import get_db
from app.services.ingestion_service import IngestionService

router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
)


@router.post("/reindex")
async def reindex(
    current_user: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int | str]:
    """Rebuild policy retrieval indexes."""
    service = IngestionService()
    result = await service.ingest(session)

    return {
        "status": "completed",
        **result,
    }
