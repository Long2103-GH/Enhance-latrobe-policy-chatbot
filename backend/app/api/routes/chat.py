"""Chat endpoints."""

import logging
import time
import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_rag_service
from app.auth.base import CurrentUser
from app.core.config import get_settings
from app.core.exceptions import GroundingError, ValidationError
from app.core.rate_limit import limiter
from app.core.security_filters import validate_input
from app.db.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

settings = get_settings()


def _client_ip(request: Request) -> str | None:
    """
    Extract the client IP, preferring the first X-Forwarded-For entry
    when the request came through a reverse proxy. Falls back to the
    direct client host.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


@router.post(
    "",
    response_model=ChatResponse,
)
@limiter.limit("10/minute")
async def chat(
    request: Request,
    response: Response,
    payload: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    rag_service: RAGService = Depends(get_rag_service),
) -> ChatResponse:
    """Answer a policy question using the RAG pipeline."""
    query = payload.query.strip()

    # ── Basic validation ──────────────────────────────────────────
    if not query:
        raise ValidationError("Question cannot be empty.")

    if len(query) > settings.max_query_length:
        raise ValidationError("Question exceeds the maximum permitted length.")

    # ── Security filter (prompt injection / XSS) ─────────────────
    if settings.input_validation_enabled:
        result = validate_input(query)
        if not result.ok:
            logger.warning(
                "Blocked input | user_id=%s | reason=%s | query=%r",
                current_user.id,
                result.reason,
                query[:100],
            )
            raise ValidationError(result.reason)
        query = result.cleaned

    # ── Network context for audit ─────────────────────────────────
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    ip_address = _client_ip(request)
    user_agent = request.headers.get("User-Agent")

    # Expose on request.state for downstream consumers (e.g. audit)
    request.state.request_id = request_id
    request.state.ip_address = ip_address
    request.state.user_agent = user_agent

    started = time.perf_counter()

    try:
        response_data = await rag_service.answer(
            session,
            query=query,
            conversation=payload.conversation,
            user_id=current_user.id,
            request_id=request_id,
            conversation_id=payload.conversation_id,
        )

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "Chat completed | request_id=%s | duration_ms=%.1f",
            request_id,
            elapsed_ms,
        )

        return response_data

    except ValidationError:
        raise

    except GroundingError as exc:
        # The LLM produced something that couldn't be grounded in the
        # retrieved evidence — this is a legitimate, expected outcome for
        # weak or ambiguous queries. Return a clean, honest message rather
        # than a system-error fallback.
        elapsed_ms = (time.perf_counter() - started) * 1000

        logger.warning(
            "Chat grounding failure [request_id=%s] after %.1f ms: %s",
            request_id,
            elapsed_ms,
            exc,
        )

        return ChatResponse(
            answer=(
                "I couldn't find enough policy evidence to answer that "
                "reliably. Try rephrasing your question — for example, be "
                "more specific about the policy area (leave, enrolment, "
                "assessment, fees). Or contact the relevant La Trobe office "
                "directly for guidance."
            ),
            citations=[],
            grounded=False,
            confidence=0.0,
            escalation_required=True,
            disclaimer=(
                "This response is not grounded in the retrieved policy "
                "documents. It is a fallback, not an answer."
            ),
            request_id=request_id,
            conversation_id=payload.conversation_id,
        )

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000

        logger.exception(
            "Chat pipeline failed [request_id=%s] after %.1f ms: %s",
            request_id,
            elapsed_ms,
            exc,
        )

        return ChatResponse(
            answer=(
                "I'm having trouble processing your request right now. "
                "Please try again in a moment. If the issue persists, "
                f"contact La Trobe University IT support and quote reference {request_id}."
            ),
            citations=[],
            grounded=False,
            confidence=0.0,
            escalation_required=True,
            disclaimer=(
                "This response was generated due to a temporary system issue "
                "and does not reflect policy information."
            ),
            request_id=request_id,
            conversation_id=payload.conversation_id,
        )
