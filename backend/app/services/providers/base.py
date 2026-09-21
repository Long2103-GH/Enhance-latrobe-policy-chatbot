"""LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Base class for all LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier — matches ``LLM_PROVIDER`` setting."""
        ...

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate a response. Raises GenerationError on failure."""
        ...
