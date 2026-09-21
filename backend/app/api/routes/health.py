"""Health endpoints."""

from fastapi import APIRouter

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
async def health() -> dict[str, str]:
    """Basic liveness check."""
    return {
        "status": "ok",
        "service": "ask-latrobe-policy-db-chatbot",
    }


@router.get("/ready")
async def readiness() -> dict[str, str]:
    """Basic readiness endpoint."""
    return {
        "status": "ready",
    }
