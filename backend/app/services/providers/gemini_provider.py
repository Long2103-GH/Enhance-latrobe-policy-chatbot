"""Gemini generation provider (fallback).

Wraps the Google GenAI SDK behind the ``LLMProvider`` interface. Same
retry semantics as DeepSeek: exponential backoff on transient errors.
"""

from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import errors, types

from app.core.config import get_settings
from app.core.exceptions import GenerationError
from app.services.providers.base import LLMProvider

logger = logging.getLogger(__name__)


_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class GeminiProvider(LLMProvider):
    """Generate responses using Gemini."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_generation_model

    @property
    def name(self) -> str:
        return "gemini"

    async def generate(self, prompt: str) -> str:
        """Generate a response with retries on transient errors."""
        max_retries = 5
        delay = 2.0

        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="text/plain",
                    ),
                )

                text = response.text
                if not text:
                    raise GenerationError("Gemini returned an empty response.")

                return text.strip()

            except errors.APIError as exc:
                status = getattr(exc, "status_code", None)
                exc_str = str(exc)

                is_transient = (
                    status in _TRANSIENT_STATUS_CODES
                    or "429" in exc_str
                    or "500" in exc_str
                    or "502" in exc_str
                    or "503" in exc_str
                    or "504" in exc_str
                    or "RESOURCE_EXHAUSTED" in exc_str
                    or "UNAVAILABLE" in exc_str
                    or "high demand" in exc_str
                )

                if is_transient and attempt < max_retries - 1:
                    logger.warning(
                        "Gemini transient error (attempt %d/%d), "
                        "retrying in %.1fs. status=%s",
                        attempt + 1,
                        max_retries,
                        delay,
                        status,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue

                logger.exception("Gemini API error during generation.")
                raise GenerationError(
                    "Gemini generation API failed.",
                    details={
                        "model": self.model,
                        "status": status,
                        "error_type": type(exc).__name__,
                    },
                ) from exc

            except GenerationError:
                raise

            except Exception as exc:
                logger.exception("Gemini generation failed unexpectedly.")
                raise GenerationError(
                    "The policy assistant could not generate a response."
                ) from exc

        raise GenerationError("Gemini retries exhausted.")
