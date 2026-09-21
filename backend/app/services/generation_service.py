"""LLM generation service with provider fallback chain.

The rest of the app calls ``GenerationService.generate(prompt)`` without
knowing which LLM provider is active. Provider selection and fallback
chaining are entirely encapsulated here.

Configuration (see ``Settings``):
    LLM_PROVIDER               primary provider: "deepseek" | "gemini" | "claude"
    LLM_FALLBACK_ENABLED       enable fallback chain (default: true)
    LLM_FALLBACK_PROVIDER      first fallback
    LLM_FALLBACK_PROVIDER_2    second fallback

On any ``GenerationError`` from the primary provider, each fallback (in
order) is tried. If every provider fails, the **primary** error is
re-raised — it's the most informative for logs and audit trail.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.exceptions import GenerationError
from app.services.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class GenerationService:
    """Generate policy-grounded responses via the configured LLM provider."""

    def __init__(self) -> None:
        settings = get_settings()

        self.primary = self._build_provider(settings.llm_provider)

        # Build the fallback chain — only providers that are configured
        # and different from the primary.
        self.fallbacks: list[LLMProvider] = []
        chain_names: list[str] = []

        for name in (
            settings.llm_fallback_provider,
            settings.llm_fallback_provider_2,
        ):
            candidate = (name or "").strip().lower()
            if (
                settings.llm_fallback_enabled
                and candidate
                and candidate != settings.llm_provider.strip().lower()
                and candidate not in {f.name for f in self.fallbacks}
            ):
                try:
                    self.fallbacks.append(self._build_provider(candidate))
                    chain_names.append(candidate)
                except GenerationError as exc:
                    logger.warning(
                        "Fallback provider '%s' could not be initialised: %s",
                        candidate,
                        exc,
                    )

        logger.info(
            "GenerationService initialised | primary=%s | fallbacks=%s",
            self.primary.name,
            chain_names if chain_names else "none",
        )

    # ─── Construction ──────────────────────────────────────────────
    @staticmethod
    def _build_provider(name: str) -> LLMProvider:
        """Construct an LLM provider by name."""
        name = (name or "").strip().lower()

        if name == "deepseek":
            from app.services.providers.deepseek_provider import DeepSeekProvider

            return DeepSeekProvider()

        if name == "gemini":
            from app.services.providers.gemini_provider import GeminiProvider

            return GeminiProvider()

        if name == "claude":
            from app.services.providers.claude_provider import ClaudeProvider

            return ClaudeProvider()

        raise GenerationError(
            f"Unknown LLM provider: {name!r}. Expected 'deepseek', 'gemini', or 'claude'."
        )

    # ─── Public API ────────────────────────────────────────────────
    async def generate(self, prompt: str) -> str:
        """
        Generate a response using the primary provider, with fallback chain.

        Raises the primary error only when every provider in the chain
        has failed.
        """
        if not isinstance(prompt, str) or not prompt.strip():
            raise GenerationError("Generation prompt must be a non-empty string.")

        try:
            return await self.primary.generate(prompt)
        except GenerationError as primary_error:
            if not self.fallbacks:
                raise

            for fallback in self.fallbacks:
                logger.warning(
                    "Primary provider '%s' failed (%s). Trying fallback '%s'.",
                    self.primary.name,
                    primary_error,
                    fallback.name,
                )
                try:
                    return await fallback.generate(prompt)
                except GenerationError:
                    logger.warning(
                        "Fallback provider '%s' also failed. "
                        "Trying next provider in chain.",
                        fallback.name,
                    )
                    continue

            logger.exception(
                "All providers in the chain failed. "
                "Raising the original primary error."
            )
            raise primary_error
