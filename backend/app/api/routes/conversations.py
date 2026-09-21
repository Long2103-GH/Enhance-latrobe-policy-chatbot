"""Conversation REST endpoints — server-side, user-scoped."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.auth.base import CurrentUser
from app.db.database import get_db
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
    ConversationRenameRequest,
    ConversationSummary,
)
from app.services.conversation_service import ConversationService

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


@router.get(
    "",
    response_model=ConversationListResponse,
)
async def list_conversations(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    """List the current user's conversations, most recent first."""
    service = ConversationService(session)
    summaries = await service.list_for_user(current_user.id)
    return ConversationListResponse(conversations=list(summaries))


@router.post(
    "",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    """Create a new empty conversation."""
    service = ConversationService(session)
    conversation = await service.create(current_user.id, title=payload.title)
    await session.commit()
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
)
async def get_conversation(
    conversation_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    """Load a single conversation with all its messages."""
    service = ConversationService(session)
    detail = await service.get_detail(conversation_id, current_user.id)
    if detail is None:
        # 404 — do not reveal whether the conversation exists for another user.
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return detail


@router.patch(
    "/{conversation_id}",
    response_model=ConversationSummary,
)
async def rename_conversation(
    conversation_id: int,
    payload: ConversationRenameRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    """Rename a conversation owned by the current user."""
    service = ConversationService(session)
    conversation = await service.rename(
        conversation_id,
        current_user.id,
        payload.title,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    await session.commit()

    # Return summary with current message count.
    details = await service.get_detail(conversation.id, current_user.id)
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(details.messages) if details else 0,
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a conversation owned by the current user."""
    service = ConversationService(session)
    deleted = await service.delete(conversation_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    await session.commit()
