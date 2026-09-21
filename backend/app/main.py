"""FastAPI application entry point."""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.router import api_router
from app.core.config import get_settings
from app.core.core_logging import configure_logging
from app.core.exceptions import ApplicationError
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.db.database import init_database
from app.middleware.security_headers import SecurityHeadersMiddleware

configure_logging()

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    try:
        await init_database()
    except Exception as exc:
        logger.exception("Failed to initialize database during startup: %s", exc)
        raise
    logger.info("Policy DB Chatbot backend started successfully.")
    yield
    logger.info("Policy DB Chatbot backend shutting down.")


app = FastAPI(
    title="La Trobe University Policy DB Chatbot API",
    description=(
        "Secure retrieval-augmented generation backend for the "
        "La Trobe University Policy Database."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.app_env.lower() == "production" else "/docs",
    redoc_url=None if settings.app_env.lower() == "production" else "/redoc",
    openapi_url=None if settings.app_env.lower() == "production" else "/openapi.json",
)


# ============================================================
# Rate limiter wiring
# ============================================================
# slowapi requires the limiter to be attached to app.state, and the
# RateLimitExceeded exception to be mapped to our handler. Without this,
# @limiter.limit(...) decorators are no-ops AND the 429 response falls
# through to the generic 500 handler.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# ============================================================
# Security headers middleware
# ============================================================
# Runs first (outermost), so its headers are added to every
# response — including errors and CORS preflights.
app.add_middleware(SecurityHeadersMiddleware)


# ============================================================
# CORS middleware
# ============================================================
# Explicit allowlist from settings. No "*" wildcard.
# In development, add your local origins via CORS_ORIGINS in .env.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


# ============================================================
# Helpers
# ============================================================
def _get_request_id(request: Request) -> str:
    """Return the request ID from state, generating one if absent."""
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _apply_cors(request: Request, response: JSONResponse) -> JSONResponse:
    """
    Attach CORS headers to a response if the request origin is allowed.

    CORSMiddleware normally handles this, but exception responses bypass
    parts of the middleware stack in some Starlette versions. Applying
    the allowlist check here guarantees consistency.
    """
    origin = request.headers.get("origin")
    if origin and origin in settings.cors_origin_list:
        response.headers["Access-Control-Allow-Origin"] = origin
    return response


# ============================================================
# Middleware — request ID
# ============================================================
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach a request ID to every request."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ============================================================
# Exception handlers
# ============================================================
@app.exception_handler(ApplicationError)
async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    """Convert domain exceptions into consistent API responses."""
    response = JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "request_id": _get_request_id(request),
        },
    )
    return _apply_cors(request, response)


@app.exception_handler(Exception)
async def unexpected_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected errors without leaking internals."""
    request_id = _get_request_id(request)

    logger.exception("Unhandled exception [request_id=%s]: %s", request_id, exc)

    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred. Please try again later.",
            "request_id": request_id,
        },
    )
    return _apply_cors(request, response)


# ============================================================
# Routes
# ============================================================
app.include_router(api_router)
