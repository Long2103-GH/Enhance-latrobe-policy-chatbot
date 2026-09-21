"""Claude (Anthropic) generation provider.

Uses the official anthropic SDK against Claude Haiku 4.5. Retries on
transient errors (429 rate limit, 529 overloaded) with exponential
backoff; non-transient errors are raised immediately as
``GenerationError``.
"""

from __future__ import annotations

import asyncio
import logging

import anthropic

from app.core.config import get_settings
from app.core.exceptions import GenerationError
from app.services.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(LLMProvider):
    """Generate responses using Claude via the Anthropic SDK."""

    def __init__(self) -> None:
        settings = get_settings()

        if not settings.claude_api_key:
            raise GenerationError("Claude selected but CLAUDE_API_KEY is not set.")

        self.client = anthropic.AsyncAnthropic(
            api_key=settings.claude_api_key,
        )
        self.model = settings.claude_model

    @property
    def name(self) -> str:
        return "claude"

    async def generate(self, prompt: str) -> str:
        """Generate a response with retries on transient errors."""
        max_retries = 4
        delay = 2.0

        for attempt in range(max_retries):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )

                text = response.content[0].text if response.content else ""
                if not text:
                    raise GenerationError("Claude returned an empty response.")

                return text.strip()

            except anthropic.RateLimitError as exc:
                # 429 — always retryable.
                if attempt < max_retries - 1:
                    logger.warning(
                        "Claude rate limit (attempt %d/%d), retrying in %.1fs",
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                logger.exception("Claude rate limit exhausted.")
                raise GenerationError("Claude rate limit exhausted.") from exc

            except anthropic.APIStatusError as exc:
                # 529 = overloaded, 5xx = transient server errors.
                status = getattr(exc, "status_code", None)
                is_transient = status in {500, 502, 503, 504, 529}

                if is_transient and attempt < max_retries - 1:
                    logger.warning(
                        "Claude transient error status=%s (attempt %d/%d), "
                        "retrying in %.1fs",
                        status,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                logger.exception("Claude API error during generation.")
                raise GenerationError(
                    "Claude generation API failed.",
                    details={
                        "model": self.model,
                        "status": status,
                        "error_type": type(exc).__name__,
                    },
                ) from exc

            except anthropic.APIConnectionError as exc:
                logger.exception("Claude connection error.")
                raise GenerationError("Claude could not be reached.") from exc

            except GenerationError:
                raise

            except Exception as exc:
                logger.exception("Claude generation failed unexpectedly.")
                raise GenerationError(
                    "The policy assistant could not generate a response."
                ) from exc

        raise GenerationError("Claude retries exhausted.")
