"""Rate limiting configuration and utilities."""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

settings = get_settings()


def _rate_limit_key(request: Request) -> str:
    """
    Extract the rate-limit key for a request.

    Priority:
    1. Authenticated user ID (if available) — fairer for shared IPs
    2. Fall back to remote IP address

    Why this ordering:
      - Universities often use NAT, so many users share one IP.
      - Keying by user_id prevents one user from exhausting another's quota.
      - For unauthenticated routes, IP is the only option.
    """
    # `request.state.user_id` is set by the auth dependency when present.
    # We use getattr defensively — auth isn't required on all routes.
    user_id = getattr(request.state, "user_id", None)

    if user_id is not None:
        return f"user:{user_id}"

    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    storage_uri="memory://",  # Use "redis://..." in multi-instance deploys
    strategy="fixed-window",
    headers_enabled=True,
)


async def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """
    Return a structured 429 response when the rate limit is exceeded.

    Matches the ErrorResponse schema used elsewhere in the API, and
    follows the same CORS allowlist policy as the rest of the app.
    """
    request_id = getattr(request.state, "request_id", "unknown")

    response = JSONResponse(
        status_code=429,
        content={
            "error": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please slow down and try again shortly.",
            "request_id": request_id,
        },
    )

    # Mirror the CORS allowlist enforced by CORSMiddleware.
    origin = request.headers.get("origin")
    if origin and origin in settings.cors_origin_list:
        response.headers["Access-Control-Allow-Origin"] = origin

    # Tell the client when to retry.
    retry_after = getattr(exc, "retry_after", None) or 60
    response.headers["Retry-After"] = str(retry_after)

    return response
