"""FastAPI dependency providers."""

from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import CurrentUser
from app.auth.factory import get_auth_provider
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.database import get_db
from app.services.audit_service import AuditService
from app.services.embedding_service import EmbeddingService
from app.services.generation_service import GenerationService
from app.services.lexical_store import LexicalStore
from app.services.query_rewriter import QueryRewriterService
from app.services.rag_service import RAGService
from app.services.reranking_service import RerankingService
from app.services.retrieval_service import RetrievalService
from app.services.validation_service import ValidationService
from app.services.vector_store import VectorStore


# auto_error=False so we can return a proper 401 (not FastAPI's default 403)
# when the Authorization header is missing.
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    session: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Resolve the current authenticated user via the active provider."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required.")

    provider = get_auth_provider()
    return await provider.verify_token(session, credentials.credentials)


async def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require administrative access."""
    if current_user.role != "admin":
        raise AuthorizationError("Administrator privileges are required.")

    return current_user


@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    """
    Construct the RAG dependency graph.

    Cached so the underlying LLM clients, Qdrant client, and embedding
    service are reused across requests rather than rebuilt on every call.
    """
    settings = get_settings()

    embedding_service = EmbeddingService()
    vector_store = VectorStore()
    lexical_store = LexicalStore()
    generation_service = GenerationService()
    reranking_service = RerankingService(
        bm25_weight=settings.reranking_bm25_weight,
    )

    query_rewriter = QueryRewriterService(
        generation_service=generation_service,
    )

    retrieval_service = RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        lexical_store=lexical_store,
        reranking_service=reranking_service,
        query_rewriter=query_rewriter,
    )

    validation_service = ValidationService()
    audit_service = AuditService()

    return RAGService(
        retrieval_service=retrieval_service,
        generation_service=generation_service,
        validation_service=validation_service,
        audit_service=audit_service,
        query_rewriter=query_rewriter,
    )