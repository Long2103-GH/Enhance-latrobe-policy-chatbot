"""Central API router."""

from fastapi import APIRouter

from app.api.routes import admin, auth, chat, conversations, health

api_router = APIRouter(
    prefix="/api/v1",
)

api_router.include_router(
    health.router,
)

api_router.include_router(
    auth.router,
)

api_router.include_router(
    conversations.router,
)

api_router.include_router(
    chat.router,
)

api_router.include_router(
    admin.router,
)
