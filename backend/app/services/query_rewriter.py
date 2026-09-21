"""Conversational query rewriting and semantic broadening.

Two distinct capabilities:

  1. rewrite() — resolves follow-up questions ("so what should I do?")
     into standalone queries. Fires only when heuristics detect a
     follow-up. Cheap: skips the LLM for self-contained queries.

  2. broaden() — when retrieval confidence is low, ask the LLM to
     rewrite the query into a broader, policy-oriented search phrase.
     Fires only when the retrieval service explicitly requests it.

Both methods fall back to the original query on any failure, so the
pipeline never breaks due to rewrite issues.
"""

import logging
import re
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.exceptions import GenerationError
from app.schemas.chat import ChatMessage
from app.services.generation_service import GenerationService

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# Heuristics: when does a query need rewriting?
# ────────────────────────────────────────────────────────────────────────

_ANAPHORA_PATTERNS = (
    r"\bit\b",
    r"\bthat\b",
    r"\bthis\b",
    r"\bthese\b",
    r"\bthose\b",
    r"\bthem\b",
    r"\bthey\b",
    r"\btheir\b",
    r"\bthe other one\b",
    r"\bthe same\b",
    r"\bso what\b",
    r"\bso how\b",
    r"\bwhat about\b",
    r"\btell me more\b",
    r"\band the\b",
    r"\band what\b",
    r"\bhow do i do that\b",
    r"\bhow does that\b",
    r"\bwhat should i do\b",
    r"\bwhat next\b",
)

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "get",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "just",
        "me",
        "more",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "out",
        "so",
        "some",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "up",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_ANAPHORA_RE = re.compile("|".join(_ANAPHORA_PATTERNS), re.IGNORECASE)

_MIN_CONTENT_TOKENS_FOR_SKIP = 2
_MAX_FOLLOWUP_LENGTH = 140


def _content_tokens(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def needs_rewrite(query: str, conversation: Sequence[ChatMessage]) -> bool:
    """Decide whether a query is likely a follow-up that needs rewriting."""
    if not conversation:
        return False

    q = (query or "").strip()
    if not q:
        return False

    if len(q) > _MAX_FOLLOWUP_LENGTH:
        return False

    if _ANAPHORA_RE.search(q):
        return True

    tokens = _content_tokens(q)
    if len(tokens) < _MIN_CONTENT_TOKENS_FOR_SKIP:
        return True

    return False


# ────────────────────────────────────────────────────────────────────────
# Follow-up rewrite prompt
# ────────────────────────────────────────────────────────────────────────

_REWRITE_SYSTEM_PROMPT = """You rewrite a user's follow-up question into a
fully self-contained question, using the previous conversation as context.

RULES:
- Output ONLY the rewritten question. No preamble, no quotes, no explanation.
- Keep it under 25 words.
- Preserve the original intent.
- If the follow-up is unclear, output the original question unchanged.
- Never invent facts, policies, or entities that aren't in the conversation.

Examples:

Previous:
USER: Is a 100% scholarship available for undergraduate international students?
ASSISTANT: There's no specific mention of 100% scholarships for international undergraduates, but La Trobe offers a range of scholarships...
Follow-up: "So what should I do to get that?"
Rewritten: "How do I apply for a 100% scholarship as an undergraduate international student?"

Previous:
USER: What is the parental leave policy?
ASSISTANT: La Trobe provides up to 14 weeks of paid parental leave...
Follow-up: "And for casual staff?"
Rewritten: "What is the parental leave policy for casual staff at La Trobe?"
"""


def _build_rewrite_user_prompt(
    query: str,
    conversation: Sequence[ChatMessage],
) -> str:
    recent = conversation[-4:]

    lines: list[str] = []
    for msg in recent:
        role = "USER" if msg.role == "user" else "ASSISTANT"
        content = (msg.content or "").strip()
        if role == "ASSISTANT" and len(content) > 500:
            content = content[:500].rstrip() + "…"
        lines.append(f"{role}: {content}")

    transcript = "\n".join(lines)

    return f"""Previous conversation:
{transcript}

Follow-up: "{query}"

Rewritten question:"""


# ────────────────────────────────────────────────────────────────────────
# Broadening prompt (for low-confidence retrieval)
# ────────────────────────────────────────────────────────────────────────

_BROADEN_SYSTEM_PROMPT = """You rewrite a user's question into a broader,
policy-oriented search phrase for a university policy database.

The original question did not match any policy closely enough. Your job
is to generalise it into a phrase that would match the policy AREA that
governs the topic — even if the specific example in the question doesn't
appear in any policy.

RULES:
- Output ONLY the rewritten search phrase. No preamble, no quotes.
- Keep it under 20 words.
- Replace specific nouns with the broader category they belong to.
- Preserve the intent — don't change what the user is asking about.
- Do NOT invent policies, section names, or answer the question.
- If the question is already broad, output it unchanged.

Examples:

Original: "can i sing in my lecture class?"
Broadened: "student behaviour and conduct in classes and lectures"

Original: "can i bring my pet to uni?"
Broadened: "animals on campus and student responsibilities"

Original: "what happens if i nap during an exam?"
Broadened: "student conduct during examinations and assessment"

Original: "is it ok to eat during a lab?"
Broadened: "student behaviour in laboratory and practical classes"

Original: "how do i defer my semester as an international student?"
Broadened: "deferment and leave of absence for international students"
"""


def _build_broaden_user_prompt(query: str) -> str:
    return f'Original: "{query}"\nBroadened:'


# ────────────────────────────────────────────────────────────────────────
# Public service
# ────────────────────────────────────────────────────────────────────────


class QueryRewriterService:
    """
    Rewrites conversational follow-ups and broadens low-confidence queries.

    Both capabilities fall back to the original query on failure.
    """

    def __init__(self, generation_service: GenerationService) -> None:
        self.settings = get_settings()
        self.generation_service = generation_service

    # ─── Follow-up rewrite ─────────────────────────────────────────
    async def rewrite(
        self,
        query: str,
        conversation: Sequence[ChatMessage],
    ) -> str:
        """Return a rewritten standalone query, or the original."""
        if not self.settings.query_rewriting_enabled:
            return query

        if not needs_rewrite(query, conversation):
            logger.debug("Query rewrite skipped (self-contained): %r", query[:80])
            return query

        try:
            rewritten = await self._call_rewrite(query, conversation)
        except GenerationError as exc:
            logger.warning("Query rewrite failed, using original: %s", exc)
            return query
        except Exception as exc:
            logger.warning("Query rewrite raised unexpected error: %s", exc)
            return query

        rewritten = self._sanitize(rewritten)
        if not rewritten or len(rewritten) > 300:
            logger.warning(
                "Query rewrite rejected (invalid output): %r", rewritten[:80]
            )
            return query

        logger.info("QUERY REWRITE | %r → %r", query, rewritten)
        return rewritten

    # ─── Semantic broadening ───────────────────────────────────────
    async def broaden(self, query: str) -> str:
        """
        Broaden a query into a policy-oriented phrase.

        Called by the retrieval service when the first-pass fused score
        is below a threshold. Falls back to the original query on any
        failure, so the caller can safely ignore exceptions.
        """
        if not self.settings.query_broadening_enabled:
            return query

        try:
            broadened = await self._call_broaden(query)
        except GenerationError as exc:
            logger.warning("Query broadening failed, using original: %s", exc)
            return query
        except Exception as exc:
            logger.warning("Query broadening raised unexpected error: %s", exc)
            return query

        broadened = self._sanitize(broadened)
        if not broadened or len(broadened) > 300:
            logger.warning(
                "Query broadening rejected (invalid output): %r", broadened[:80]
            )
            return query

        if broadened.lower() == query.lower():
            logger.debug("Query broadening returned identical text; skipping.")
            return query

        logger.info("QUERY BROADEN | %r → %r", query, broadened)
        return broadened

    # ─── Internals ─────────────────────────────────────────────────
    async def _call_rewrite(
        self,
        query: str,
        conversation: Sequence[ChatMessage],
    ) -> str:
        prompt = (
            _REWRITE_SYSTEM_PROMPT
            + "\n\n"
            + _build_rewrite_user_prompt(query, conversation)
        )
        return await self.generation_service.generate(prompt)

    async def _call_broaden(self, query: str) -> str:
        prompt = _BROADEN_SYSTEM_PROMPT + "\n\n" + _build_broaden_user_prompt(query)
        return await self.generation_service.generate(prompt)

    @staticmethod
    def _sanitize(text: str) -> str:
        t = (text or "").strip()
        for prefix in (
            "Rewritten question:",
            "Rewritten:",
            "Question:",
            "Broadened:",
            "Search phrase:",
            "Phrase:",
        ):
            if t.lower().startswith(prefix.lower()):
                t = t[len(prefix) :].strip()
        while (
            len(t) >= 2
            and t[0] in ('"', "'", "“", "‘")
            and t[-1] in ('"', "'", "”", "’")
        ):
            t = t[1:-1].strip()
        t = " ".join(t.split())
        return t

