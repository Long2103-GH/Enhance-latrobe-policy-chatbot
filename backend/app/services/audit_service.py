"""Audit logging service."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent

logger = logging.getLogger(__name__)


class AuditService:
    """Persist security and RAG audit events."""

    async def record(
        self,
        session: AsyncSession,
        *,
        request_id: str,
        event_type: str,
        user_id: int | None,
        query: str | None,
        retrieved_chunk_count: int | None,
        retrieval_score: float | None,
        grounding_score: float | None,
        success: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
        response_time_ms: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Create an audit record without storing raw sensitive queries.

        The query is hashed with SHA-256 before storage. The hash is
        stable (same query → same hash) but cannot be reversed, which
        satisfies privacy requirements while still allowing abuse
        detection (repeated identical queries show as repeated hashes).
        """
        if not request_id or not event_type:
            raise ValueError(
                "request_id and event_type are required for audit logging."
            )

        query_hash: str | None = None
        if query:
            query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()

        # Truncate the user agent to the column's max length if exceeded.
        if user_agent and len(user_agent) > 500:
            user_agent = user_agent[:500]

        event = AuditEvent(
            request_id=request_id,
            event_type=event_type,
            user_id=user_id,
            query_hash=query_hash,
            retrieved_chunk_count=retrieved_chunk_count,
            retrieval_score=retrieval_score,
            grounding_score=grounding_score,
            ip_address=ip_address,
            user_agent=user_agent,
            response_time_ms=response_time_ms,
            success=success,
            details=(json.dumps(details, ensure_ascii=False) if details else None),
        )

        session.add(event)
        await session.commit()
