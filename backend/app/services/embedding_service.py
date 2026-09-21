"""Hugging Face Inference API embedding service implementation.

Optimized for full-corpus ingestion:
  - Larger batch size (64) → fewer API calls
  - Retry with exponential backoff on transient errors
  - Progress logging per batch
"""

from __future__ import annotations

import asyncio
import logging

from huggingface_hub import AsyncInferenceClient

from app.core.config import get_settings
from app.core.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings via the Hugging Face Inference API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncInferenceClient(
            model=settings.embedding_model,
            token=settings.hf_token,
        )
        self.dimension = settings.embedding_dimension
        self.model_name = settings.embedding_model

    async def embed(self, text: str) -> list[float]:
        """Generate a vector embedding for a single text."""
        if not isinstance(text, str) or not text.strip():
            raise RetrievalError(
                "Embedding text must be a non-empty string.",
                details={"operation": "embed"},
            )

        try:
            response = await self.client.feature_extraction(text)

            if (
                isinstance(response, list)
                and response
                and isinstance(response[0], list)
            ):
                vector = response[0]
            else:
                vector = response

            return [float(x) for x in vector]

        except Exception as exc:
            logger.exception("Hugging Face API error during single embedding.")
            raise RetrievalError(
                "Hugging Face embedding API failed for single text.",
                details={
                    "operation": "embed",
                    "text_length": len(text),
                    "error_type": type(exc).__name__,
                },
            ) from exc

    async def embed_many(
        self,
        texts: list[str],
        batch_size: int = 64,
        max_retries: int = 3,
    ) -> list[list[float]]:
        """
        Embed multiple texts in batches.

        Retries transient failures (429, 5xx, timeouts) with exponential
        backoff. Logs progress every batch so long ingestions are visible.
        """
        vectors: list[list[float]] = []
        total = len(texts)
        total_batches = (total + batch_size - 1) // batch_size

        for batch_index, i in enumerate(range(0, total, batch_size), start=1):
            batch = texts[i : i + batch_size]

            logger.info(
                "Embedding batch %d/%d (%d chunks)...",
                batch_index,
                total_batches,
                len(batch),
            )

            response = await self._embed_batch_with_retry(
                batch,
                max_retries=max_retries,
            )

            for item in response:
                if isinstance(item, list) and item and isinstance(item[0], list):
                    vectors.append([float(x) for x in item[0]])
                else:
                    vectors.append([float(x) for x in item])

            logger.info(
                "Batch %d/%d done — total embeddings: %d/%d",
                batch_index,
                total_batches,
                len(vectors),
                total,
            )

        return vectors

    async def _embed_batch_with_retry(
        self,
        batch: list[str],
        max_retries: int = 3,
    ) -> list:
        """Call HF feature_extraction with exponential backoff."""
        delay = 2.0
        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                return await self.client.feature_extraction(batch)
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)

                is_rate_limit = (
                    "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "Too Many Requests" in err_str
                )
                is_transient = (
                    is_rate_limit
                    or "503" in err_str
                    or "504" in err_str
                    or "timeout" in err_str.lower()
                )

                if is_transient and attempt < max_retries - 1:
                    logger.warning(
                        "HF batch failed (%s), retrying in %.1fs (attempt %d/%d)",
                        type(exc).__name__,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                logger.exception("Hugging Face API error during batch embedding.")
                raise RetrievalError(
                    "Hugging Face embedding API failed for batch.",
                    details={
                        "operation": "embed_many",
                        "batch_size": len(batch),
                        "error_type": type(exc).__name__,
                        "attempts": attempt + 1,
                    },
                ) from exc

        raise RetrievalError(
            "Hugging Face embedding API failed for batch.",
            details={
                "operation": "embed_many",
                "batch_size": len(batch),
                "error_type": type(last_exc).__name__ if last_exc else "unknown",
                "attempts": max_retries,
            },
        ) from last_exc
