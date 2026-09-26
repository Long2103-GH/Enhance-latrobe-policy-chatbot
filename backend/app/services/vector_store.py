"""Qdrant vector store implementation."""

import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import get_settings
from app.core.exceptions import RetrievalError
from app.rag.models import PolicyChunkData, RetrievalResult

logger = logging.getLogger(__name__)


class VectorStore:
    """Persistent semantic vector store."""

    def __init__(self) -> None:
        settings = get_settings()

        if settings.qdrant_mode == "local":
            self.client = AsyncQdrantClient(
                path=settings.qdrant_path,
            )
        else:
            if not settings.qdrant_url:
                raise ValueError(
                    "QDRANT_URL is required when QDRANT_MODE is not local."
                )

            self.client = AsyncQdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
            )

        self.collection_name = settings.qdrant_collection
        self.dimension = settings.embedding_dimension

    async def ensure_collection(self) -> None:
        """Create the collection if it does not exist."""
        exists = await self.client.collection_exists(self.collection_name)

        if exists:
            return

        await self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.dimension,
                distance=models.Distance.COSINE,
            ),
        )

    async def upsert(
        self,
        chunks: list[PolicyChunkData],
        vectors: list[list[float]],
    ) -> None:
        """Insert or replace vectors."""
        if len(chunks) != len(vectors):
            raise ValueError("Number of chunks and vectors must match.")

        points: list[models.PointStruct] = []

        for chunk, vector in zip(chunks, vectors, strict=True):
            point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id))

            points.append(
                models.PointStruct(
                    id=point_uuid,
                    vector=vector,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "policy_id": chunk.policy_external_id,
                        "title": chunk.title,
                        "url": chunk.url,
                        "section": chunk.section,
                        "text": chunk.text,
                        "chunk_index": chunk.chunk_index,
                    },
                )
            )

        if points:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )

    async def search(
        self,
        vector: list[float],
        limit: int,
    ) -> list[RetrievalResult]:
        """Perform semantic similarity search using query_points."""
        try:
            response = await self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit,
                with_payload=True,
            )

            output: list[RetrievalResult] = []

            for result in response.points:
                payload: dict[str, Any] = result.payload or {}

                output.append(
                    RetrievalResult(
                        chunk_id=str(payload["chunk_id"]),
                        policy_id=str(payload["policy_id"]),
                        title=str(payload["title"]),
                        section=str(payload["section"]),
                        text=str(payload["text"]),
                        url=str(payload["url"]),
                        vector_score=float(result.score),
                        lexical_score=0.0,
                        fused_score=0.0,
                    )
                )

            return output

        except Exception as exc:
            logger.exception("Vector search failed.")
            raise RetrievalError(
                "Qdrant vector search failed.",
                details={
                    "collection": self.collection_name,
                    "error_type": type(exc).__name__,
                },
            ) from exc
