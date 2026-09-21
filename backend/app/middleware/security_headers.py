"""Security headers middleware.

Adds defense-in-depth HTTP response headers to every response:

  - Content-Security-Policy:     restrict script/style/connect sources
  - Strict-Transport-Security:   force HTTPS for future requests
  - X-Content-Type-Options:      prevent MIME-type sniffing
  - X-Frame-Options:             prevent clickjacking via iframes
  - Referrer-Policy:             limit referrer leakage on outbound links
  - Permissions-Policy:          disable browser features we don't use

Two CSP policies are used:

  1. STRICT — used for all API responses.
     No `unsafe-inline` scripts, no external CDNs beyond jsDelivr
     (which the frontend uses for marked.js and DOMPurify).

  2. DOCS — used only for /docs, /redoc, /openapi.json.
     Allows Swagger UI's inline bootstrap script, jsDelivr CSS, and
     FastAPI's favicon. The narrower scope means the app's own API
     responses keep the strict policy.

Swagger docs can be disabled entirely in production (see ``main.py``),
in which case the DOCS policy is simply never applied.

Toggle the whole middleware via ``settings.security_headers_enabled``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import MappingProxyType

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# CSP policies
# ---------------------------------------------------------------------------

_CSP_STRICT: str = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

_CSP_DOCS: str = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self' https://cdn.jsdelivr.net; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


_DOCS_PATHS: tuple[str, ...] = ("/docs", "/redoc", "/openapi.json")


# Static headers applied to every response.
# Note: HSTS is set unconditionally — browsers ignore it on localhost,
# so this is safe in development. Only HTTPS-deployed origins honor it.
_BASE_HEADERS: MappingProxyType = MappingProxyType(
    {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": (
            "camera=(), microphone=(self), geolocation=(), payment=(), usb=()"
        ),
    }
)


def _is_docs_path(path: str) -> bool:
    """True when the request is for the interactive API docs."""
    return any(path == p or path.startswith(p + "/") for p in _DOCS_PATHS)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers to every outgoing HTTP response.

    Chooses the CSP based on the request path (docs vs. everything else).
    Does not touch the response body — only headers.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Process the request and inject secure HTTP response headers."""
        response = await call_next(request)

        settings = get_settings()
        if not settings.security_headers_enabled:
            return response

        for name, value in _BASE_HEADERS.items():
            if name not in response.headers:
                response.headers[name] = value

        csp = _CSP_DOCS if _is_docs_path(request.url.path) else _CSP_STRICT
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = csp

        return response
