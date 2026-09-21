"""Policy ingestion and indexing service."""

import json
import logging
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Policy, PolicyChunk
from app.rag.chunker import PolicyChunker, RawPolicy
from app.rag.models import PolicyChunkData
from app.services.embedding_service import EmbeddingService
from app.services.lexical_store import LexicalStore
from app.services.vector_store import VectorStore
from app.utils.hashing import sha256_text

logger = logging.getLogger(__name__)


class IngestionService:
    """Load policy JSONL into relational, lexical and vector indexes."""

    def __init__(self) -> None:
        settings = get_settings()

        self.policy_path = settings.policy_jsonl_path

        self.chunker = PolicyChunker()
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self.lexical_store = LexicalStore()

    async def ingest(
        self,
        session: AsyncSession,
    ) -> dict[str, int]:
        """Perform a full deterministic ingestion."""
        policies = self._load_jsonl()

        await self.vector_store.ensure_collection()

        policy_count = 0
        chunk_count = 0

        total_policies = len(policies)

        logger.info("Starting ingestion of %d policies...", total_policies)

        for index, raw in enumerate(policies, start=1):
            policy = RawPolicy(
                external_id=self._extract_external_id(raw),
                title=str(raw["title"]),
                url=str(raw["url"]),
                crawled_at=raw.get("crawled_at"),
                sections=list(raw.get("sections", [])),
            )

            chunks = self.chunker.chunk(policy)

            await self._persist_policy(session, policy, chunks)

            logger.info(
                "[%d/%d] Embedding %d chunks for: %s",
                index,
                total_policies,
                len(chunks),
                policy.title[:60],
            )

            vectors = await self.embedding_service.embed_many(
                [chunk.text for chunk in chunks]
            )

            await self.vector_store.upsert(chunks, vectors)

            policy_count += 1
            chunk_count += len(chunks)

            logger.info(
                "[%d/%d] Done — policies=%d chunks=%d",
                index,
                total_policies,
                policy_count,
                chunk_count,
            )

        await self.lexical_store.rebuild(session)

        logger.info(
            "Policy ingestion completed: %s policies, %s chunks.",
            policy_count,
            chunk_count,
        )

        return {
            "policies": policy_count,
            "chunks": chunk_count,
        }

    async def _persist_policy(
        self,
        session: AsyncSession,
        policy: RawPolicy,
        chunks: list[PolicyChunkData],
    ) -> None:
        """Persist policy metadata and chunks."""
        existing = await session.execute(
            select(Policy).where(Policy.external_id == policy.external_id)
        )
        policy_record = existing.scalar_one_or_none()

        full_text = "\n\n".join(chunk.text for chunk in chunks)
        content_hash = sha256_text(full_text)

        if policy_record is None:
            policy_record = Policy(
                external_id=policy.external_id,
                title=policy.title,
                url=policy.url,
                crawled_at=self._parse_datetime(policy.crawled_at),
                content_hash=content_hash,
                section_count=len(policy.sections),
            )
            session.add(policy_record)
            await session.flush()
        else:
            policy_record.title = policy.title
            policy_record.url = policy.url
            policy_record.crawled_at = self._parse_datetime(policy.crawled_at)
            policy_record.content_hash = content_hash
            policy_record.section_count = len(policy.sections)

            await session.execute(
                delete(PolicyChunk).where(PolicyChunk.policy_id == policy_record.id)
            )

        for chunk in chunks:
            session.add(
                PolicyChunk(
                    chunk_id=chunk.chunk_id,
                    policy_id=policy_record.id,
                    section_heading=chunk.section,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    content_hash=chunk.content_hash,
                    token_estimate=chunk.token_estimate,
                )
            )

        await session.commit()

    def _load_jsonl(self) -> list[dict]:
        """Load and validate policy records from JSONL."""
        policies: list[dict] = []

        with open(self.policy_path, "r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON on line {line_number}.") from exc

                required = {"url", "title", "sections"}
                missing = required - record.keys()

                if missing:
                    raise ValueError(
                        f"Line {line_number} missing fields: {sorted(missing)}"
                    )

                if not isinstance(record["sections"], list):
                    raise ValueError(f"Line {line_number}: sections must be a list.")

                policies.append(record)

        return policies

    @staticmethod
    def _extract_external_id(record: dict) -> str:
        """Extract a stable policy ID from its URL."""
        url = str(record["url"])

        if "id=" in url:
            return url.split("id=", 1)[1].split("&", 1)[0]

        return sha256_text(url)[:32]

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        """Parse the crawler timestamp."""
        if not value:
            return None

        return datetime.fromisoformat(value.replace("Z", "+00:00"))
