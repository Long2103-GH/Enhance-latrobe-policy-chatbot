"""Policy-aware document chunking."""

from dataclasses import dataclass

from app.rag.models import PolicyChunkData
from app.utils.hashing import sha256_text
from app.utils.text import estimate_tokens, normalize_text


@dataclass(slots=True, frozen=True)
class RawPolicy:
    """Policy structure loaded from JSONL."""

    external_id: str
    title: str
    url: str
    crawled_at: str | None
    sections: list[dict[str, str]]


class PolicyChunker:
    """
    Convert policy sections into retrieval-friendly chunks.

    The algorithm prefers semantic section boundaries and only splits a
    section when it becomes too large.
    """

    def __init__(
        self,
        max_characters: int = 3200,
        overlap_characters: int = 400,
    ) -> None:
        if max_characters <= overlap_characters:
            raise ValueError("max_characters must be greater than overlap_characters")

        self.max_characters = max_characters
        self.overlap_characters = overlap_characters

    def chunk(self, policy: RawPolicy) -> list[PolicyChunkData]:
        """Create deterministic chunks for a policy."""

        chunks: list[PolicyChunkData] = []
        chunk_index = 0

        for section in policy.sections:
            heading = normalize_text(section.get("heading", ""))
            text = normalize_text(section.get("text", ""))

            if not text:
                continue

            section_text = f"{heading}\n\n{text}"
            pieces = self._split_text(section_text)

            for piece in pieces:
                normalized = normalize_text(piece)

                if not normalized:
                    continue

                # Deterministic ID: {external_id}-{index}-{content_hash[:12]}.
                # Reproducible across runs for identical input.
                chunk_id = (
                    f"{policy.external_id}-"
                    f"{chunk_index}-"
                    f"{sha256_text(normalized)[:12]}"
                )

                chunks.append(
                    PolicyChunkData(
                        chunk_id=chunk_id,
                        policy_external_id=policy.external_id,
                        title=policy.title,
                        url=policy.url,
                        section=heading,
                        chunk_index=chunk_index,
                        text=normalized,
                        content_hash=sha256_text(normalized),
                        token_estimate=estimate_tokens(normalized),
                    )
                )

                chunk_index += 1

        return chunks

    def _split_text(self, text: str) -> list[str]:
        """Split oversized text while maintaining overlap."""

        if len(text) <= self.max_characters:
            return [text]

        pieces: list[str] = []
        start = 0

        while start < len(text):
            end = min(start + self.max_characters, len(text))

            if end < len(text):
                paragraph_break = text.rfind("\n\n", start, end)
                sentence_break = text.rfind(". ", start, end)

                if paragraph_break > start + self.max_characters // 2:
                    end = paragraph_break
                elif sentence_break > start + self.max_characters // 2:
                    end = sentence_break + 1

            piece = text[start:end].strip()

            if piece:
                pieces.append(piece)

            if end >= len(text):
                break

            next_start = max(start + 1, end - self.overlap_characters)
            start = next_start

        return pieces
