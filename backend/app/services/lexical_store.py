"""SQLite FTS5 lexical retrieval."""

import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RetrievalError
from app.rag.models import RetrievalResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query preparation
# ---------------------------------------------------------------------------

# Standard English stopwords. This list intentionally excludes any
# domain-specific terms — it is a general-purpose list, not a policy
# vocabulary. Removing these tokens stops FTS5 from matching the entire
# corpus on words like "the", "and", "in".
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "but",
        "by",
        "can",
        "cannot",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "done",
        "for",
        "from",
        "get",
        "gets",
        "getting",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "might",
        "more",
        "most",
        "must",
        "my",
        "no",
        "nor",
        "not",
        "of",
        "on",
        "or",
        "our",
        "ours",
        "out",
        "over",
        "own",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "us",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
    }
)

# Strip characters that are not part of a word. Preserves hyphens and
# apostrophes inside words (e.g. "course-work", "student's"), but drops
# trailing/leading punctuation like "?" or "." from tokens.
_TOKEN_CLEAN_RE = re.compile(r"[^\w\-']+", re.UNICODE)


class LexicalStore:
    """Keyword-based policy retrieval using SQLite FTS5."""

    async def ensure_index(self, session: AsyncSession) -> None:
        """Create the FTS5 virtual table."""
        await session.execute(text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS policy_chunks_fts
                USING fts5(
                    chunk_id UNINDEXED,
                    title,
                    section,
                    content
                )
                """))
        await session.commit()

    async def rebuild(self, session: AsyncSession) -> None:
        """Rebuild the complete FTS index."""
        await self.ensure_index(session)

        await session.execute(text("DELETE FROM policy_chunks_fts"))

        await session.execute(text("""
                INSERT INTO policy_chunks_fts (
                    chunk_id, title, section, content
                )
                SELECT
                    pc.chunk_id,
                    p.title,
                    pc.section_heading,
                    pc.text
                FROM policy_chunks pc
                INNER JOIN policies p
                    ON p.id = pc.policy_id
                """))
        await session.commit()

    async def search(
        self,
        session: AsyncSession,
        query: str,
        limit: int,
    ) -> list[RetrievalResult]:
        """
        Perform full-text keyword retrieval.

        Returns an empty list when the query has no usable content
        tokens (e.g. "hi", "what about it"). This avoids FTS5 matching
        the entire corpus on stopwords.
        """
        prepared = self._prepare_query(query)

        if not prepared:
            logger.debug("FTS skipped — no content tokens in query.")
            return []

        try:
            result = await session.execute(
                text("""
                    SELECT
                        f.chunk_id,
                        f.title,
                        f.section,
                        f.content,
                        p.external_id AS policy_id,
                        p.url,
                        bm25(policy_chunks_fts) AS rank
                    FROM policy_chunks_fts f
                    INNER JOIN policy_chunks pc
                        ON pc.chunk_id = f.chunk_id
                    INNER JOIN policies p
                        ON p.id = pc.policy_id
                    WHERE policy_chunks_fts MATCH :query
                    ORDER BY rank
                    LIMIT :limit
                    """),
                {"query": prepared, "limit": limit},
            )

            rows = result.mappings().all()

            output: list[RetrievalResult] = []
            for row in rows:
                # SQLite FTS5 BM25 is negative where lower is better.
                raw_rank = float(row["rank"])
                lexical_score = 1.0 / (1.0 + abs(raw_rank))

                output.append(
                    RetrievalResult(
                        chunk_id=str(row["chunk_id"]),
                        policy_id=str(row["policy_id"]),
                        title=str(row["title"]),
                        section=str(row["section"]),
                        text=str(row["content"]),
                        url=str(row["url"]),
                        vector_score=0.0,
                        lexical_score=lexical_score,
                        fused_score=0.0,
                    )
                )

            return output

        except Exception as exc:
            logger.exception("Lexical search failed.")
            raise RetrievalError(
                "SQLite FTS5 lexical search failed.",
                details={
                    "query_length": len(query),
                    "error_type": type(exc).__name__,
                },
            ) from exc

    # ─── Query preparation ─────────────────────────────────────────
    @staticmethod
    def _prepare_query(query: str) -> str:
        """
        Build a safe FTS5 MATCH query from user input.

        - Strips punctuation from each token.
        - Removes stopwords (general English list, no domain terms).
        - Returns an empty string if nothing usable remains.

        Tokens are joined with OR so a document matching any content
        word is a candidate. Ranking (BM25) sorts them.
        """
        if not query:
            return ""

        raw_tokens = query.lower().split()
        tokens: list[str] = []

        for raw in raw_tokens:
            cleaned = _TOKEN_CLEAN_RE.sub("", raw).strip("-'_")
            if not cleaned:
                continue
            if cleaned in _STOPWORDS:
                continue
            if len(cleaned) < 2:
                continue
            tokens.append(cleaned)

        if not tokens:
            return ""

        # De-duplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                unique.append(t)

        # Cap to avoid pathological queries.
        unique = unique[:20]

        # Quote each token to keep FTS5 operators out.
        return " OR ".join(f'"{t}"' for t in unique)
