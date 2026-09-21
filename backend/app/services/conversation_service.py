"""Conversation persistence — server-side, user-scoped.

Every method enforces ownership: a user can only read or modify their
own conversations. Cross-user access is impossible by design.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, ConversationMessage, utc_now
from app.schemas.conversation import (
    ConversationDetail,
    ConversationMessageRecord,
    ConversationSummary,
)
from app.schemas.policy import PolicyCitation

logger = logging.getLogger(__name__)


class ConversationService:
    """User-scoped conversation CRUD."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── Create ────────────────────────────────────────────────────────
    async def create(
        self,
        user_id: int,
        title: str | None = None,
    ) -> Conversation:
        """Create a new conversation owned by ``user_id``."""
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer.")

        conversation = Conversation(
            user_id=user_id,
            title=(title or "New enquiry")[:200],
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    # ─── Read (single) ─────────────────────────────────────────────────
    async def get_owned(
        self,
        conversation_id: int,
        user_id: int,
    ) -> Conversation | None:
        """
        Return the conversation iff it belongs to ``user_id``.

        Callers should treat ``None`` as "not found" — the API must not
        distinguish between "doesn't exist" and "not yours".
        """
        if conversation_id <= 0 or user_id <= 0:
            return None

        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    # ─── Read (list) ───────────────────────────────────────────────────
    async def list_for_user(
        self,
        user_id: int,
        limit: int = 100,
    ) -> Sequence[ConversationSummary]:
        """
        Return the user's conversations, most recently updated first.

        Includes a message count per conversation (single query using a
        subquery + group by).
        """
        count_subq = (
            select(
                ConversationMessage.conversation_id,
                func.count(ConversationMessage.id).label("message_count"),
            )
            .group_by(ConversationMessage.conversation_id)
            .subquery()
        )

        stmt = (
            select(
                Conversation,
                func.coalesce(count_subq.c.message_count, 0),
            )
            .outerjoin(
                count_subq,
                count_subq.c.conversation_id == Conversation.id,
            )
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        summaries = [
            ConversationSummary(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=int(count or 0),
            )
            for conv, count in rows
        ]
        return summaries

    async def get_detail(
        self,
        conversation_id: int,
        user_id: int,
    ) -> ConversationDetail | None:
        """Return full conversation detail if owned by ``user_id``, else None."""
        conversation = await self.get_owned(conversation_id, user_id)
        if conversation is None:
            return None

        result = await self.session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.id.asc())
        )
        messages = result.scalars().all()

        return ConversationDetail(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[self._to_message_record(m) for m in messages],
        )

    # ─── Rename ────────────────────────────────────────────────────────
    async def rename(
        self,
        conversation_id: int,
        user_id: int,
        new_title: str,
    ) -> Conversation | None:
        """Rename a conversation owned by ``user_id``."""
        conversation = await self.get_owned(conversation_id, user_id)
        if conversation is None:
            return None
        conversation.title = new_title.strip()[:200] or conversation.title
        conversation.updated_at = utc_now()
        await self.session.flush()
        return conversation

    # ─── Delete ────────────────────────────────────────────────────────
    async def delete(
        self,
        conversation_id: int,
        user_id: int,
    ) -> bool:
        """Delete a conversation owned by ``user_id``. Returns True if deleted."""
        conversation = await self.get_owned(conversation_id, user_id)
        if conversation is None:
            return False

        await self.session.execute(
            delete(Conversation).where(Conversation.id == conversation.id)
        )
        await self.session.flush()
        return True

    # ─── Append messages ───────────────────────────────────────────────
    async def append_exchange(
        self,
        conversation_id: int,
        user_id: int,
        user_content: str,
        assistant_content: str,
        assistant_citations: list[PolicyCitation] | None = None,
    ) -> None:
        """
        Append a user message and its assistant reply, then bump
        ``updated_at``. Auto-generates a title from the user's first
        message if the conversation is still titled "New enquiry".
        """
        conversation = await self.get_owned(conversation_id, user_id)
        if conversation is None:
            # Defensive: caller must ensure ownership; bail silently.
            return

        if conversation.title in ("", "New enquiry"):
            first_line = (
                user_content.strip().splitlines()[0] if user_content.strip() else ""
            )
            title = (first_line[:42] + "…") if len(first_line) > 42 else first_line
            conversation.title = title or "New enquiry"

        user_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content=user_content,
            citations_json=None,
        )
        self.session.add(user_msg)

        citations_payload = None
        if assistant_citations:
            citations_payload = json.dumps(
                [c.model_dump(mode="json") for c in assistant_citations],
                ensure_ascii=False,
            )

        assistant_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_content,
            citations_json=citations_payload,
        )
        self.session.add(assistant_msg)

        # NOTE: `onupdate=utc_now` on the column does NOT fire when a
        # no-op assignment is made. Set explicitly.
        conversation.updated_at = utc_now()

        await self.session.flush()

    # ─── Helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _to_message_record(msg: ConversationMessage) -> ConversationMessageRecord:
        citations: list[PolicyCitation] = []
        if msg.citations_json:
            try:
                raw = json.loads(msg.citations_json)
                citations = [PolicyCitation(**item) for item in raw]
            except Exception:
                logger.warning("Failed to parse citations for message %s", msg.id)
        return ConversationMessageRecord(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            citations=citations,
            created_at=msg.created_at,
        )
