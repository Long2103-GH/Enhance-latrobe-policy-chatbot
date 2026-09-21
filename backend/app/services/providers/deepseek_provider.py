"""DeepSeek generation provider.

Uses the OpenAI Python SDK against DeepSeek's OpenAI-compatible API.
Retries on transient errors (429, 5xx) with exponential backoff;
non-transient errors are raised immediately as ``GenerationError``.
"""

from __future__ import annotations

import asyncio
import logging

from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError

from app.core.config import get_settings
from app.core.exceptions import GenerationError
from app.services.providers.base import LLMProvider

logger = logging.getLogger(__name__)


# HTTP statuses worth retrying: 429 (rate limit), 500-504 (transient server).
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class DeepSeekProvider(LLMProvider):
    """Generate responses using DeepSeek via the OpenAI SDK."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = settings.deepseek_model

    @property
    def name(self) -> str:
        return "deepseek"

    async def generate(self, prompt: str) -> str:
        """Generate a response with retries on transient errors."""
        max_retries = 5
        delay = 2.0

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.choices[0].message.content
                if not text:
                    raise GenerationError("DeepSeek returned an empty response.")
                return text.strip()

            except RateLimitError as exc:
                # 429 — always retryable.
                if attempt < max_retries - 1:
                    logger.warning(
                        "DeepSeek rate limit (attempt %d/%d), retrying in %.1fs",
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise GenerationError("DeepSeek rate limit exhausted.") from exc

            except APIError as exc:
                status = getattr(exc, "status_code", None)
                is_transient = status in _TRANSIENT_STATUS_CODES

                if is_transient and attempt < max_retries - 1:
                    logger.warning(
                        "DeepSeek transient error %s (attempt %d/%d), retrying in %.1fs",
                        status,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                logger.exception("DeepSeek API error.")
                raise GenerationError(
                    "DeepSeek generation API failed.",
                    details={"status": status, "type": type(exc).__name__},
                ) from exc

            except APIConnectionError as exc:
                logger.exception("DeepSeek connection error.")
                raise GenerationError("DeepSeek unreachable.") from exc

            except GenerationError:
                raise

            except Exception as exc:
                logger.exception("DeepSeek unexpected error.")
                raise GenerationError(
                    "The policy assistant could not generate a response."
                ) from exc

        raise GenerationError("DeepSeek retries exhausted.")
