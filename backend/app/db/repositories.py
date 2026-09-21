"""Repository layer for database access.

Repositories encapsulate SQLAlchemy queries so that services stay
focused on business logic. Each repository owns one aggregate.

NOTE: This module is currently unused — services and routes query the
session directly. It is retained as a scaffold for future extraction
of query logic when the app grows beyond a handful of services.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, Policy, PolicyChunk, User, utc_now


# ---------------------------------------------------------------------------
# User repository
# ---------------------------------------------------------------------------
class UserRepository:
    """Data access for users."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Fetch a user by primary key."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by normalized email address."""
        normalized = email.lower().strip()
        result = await self.session.execute(
            select(User).where(User.email == normalized)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        role: str = "user",
        is_active: bool = True,
    ) -> User:
        """Insert a new user and return it."""
        user = User(
            email=email.lower().strip(),
            full_name=full_name,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
        )
        self.session.add(user)
        await self.session.flush()
        return user


# ---------------------------------------------------------------------------
# Policy repository
# ---------------------------------------------------------------------------
class PolicyRepository:
    """Data access for policies and their chunks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_external_id(self, external_id: str) -> Policy | None:
        """Fetch a policy by its external identifier."""
        result = await self.session.execute(
            select(Policy).where(Policy.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def upsert_policy(
        self,
        *,
        external_id: str,
        title: str,
        url: str,
        crawled_at: datetime | None,
        content_hash: str,
        section_count: int,
    ) -> Policy:
        """
        Insert or update a policy by external ID.

        Deletes existing chunks on update — the caller is responsible
        for re-inserting them.
        """
        existing = await self.get_by_external_id(external_id)

        if existing is None:
            policy = Policy(
                external_id=external_id,
                title=title,
                url=url,
                crawled_at=crawled_at,
                content_hash=content_hash,
                section_count=section_count,
            )
            self.session.add(policy)
            await self.session.flush()
            return policy

        existing.title = title
        existing.url = url
        existing.crawled_at = crawled_at
        existing.content_hash = content_hash
        existing.section_count = section_count
        existing.updated_at = utc_now()

        await self.session.execute(
            delete(PolicyChunk).where(PolicyChunk.policy_id == existing.id)
        )
        return existing

    async def add_chunks(
        self,
        policy_id: int,
        chunks: Sequence[dict],
    ) -> None:
        """Bulk-insert chunks for a policy."""
        for chunk in chunks:
            self.session.add(
                PolicyChunk(
                    chunk_id=chunk["chunk_id"],
                    policy_id=policy_id,
                    section_heading=chunk["section_heading"],
                    chunk_index=chunk["chunk_index"],
                    text=chunk["text"],
                    content_hash=chunk["content_hash"],
                    token_estimate=chunk["token_estimate"],
                )
            )

    async def count_policies(self) -> int:
        """Return the total number of policies."""
        result = await self.session.execute(select(func.count()).select_from(Policy))
        return result.scalar_one()

    async def count_chunks(self) -> int:
        """Return the total number of chunks."""
        result = await self.session.execute(
            select(func.count()).select_from(PolicyChunk)
        )
        return result.scalar_one()


# ---------------------------------------------------------------------------
# Audit repository
# ---------------------------------------------------------------------------
class AuditRepository:
    """Data access for audit events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        request_id: str,
        event_type: str,
        user_id: int | None,
        query_hash: str | None,
        retrieved_chunk_count: int | None,
        retrieval_score: float | None,
        grounding_score: float | None,
        success: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
        response_time_ms: float | None = None,
        details: str | None = None,
    ) -> AuditEvent:
        """Insert a new audit event."""
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
            details=details,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_recent(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        user_id: int | None = None,
    ) -> Sequence[AuditEvent]:
        """Fetch recent audit events with optional filters."""
        query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)

        if event_type is not None:
            query = query.where(AuditEvent.event_type == event_type)
        if user_id is not None:
            query = query.where(AuditEvent.user_id == user_id)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_failures_since(self, since: datetime) -> int:
        """Count failed audit events since a given time."""
        result = await self.session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.success.is_(False))
            .where(AuditEvent.created_at >= since)
        )
        return result.scalar_one()
