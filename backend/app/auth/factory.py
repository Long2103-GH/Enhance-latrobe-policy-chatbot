"""Auth provider factory.

Returns the active auth provider based on the ``AUTH_PROVIDER`` setting.
The rest of the app calls ``get_auth_provider()`` and receives a
provider — it never constructs one directly.

Because Auth0Provider needs env vars at construction time and JWTProvider
doesn't, we cache the instance. A single process uses one provider for
its lifetime, which matches how a deployment works: each environment
gets one ``AUTH_PROVIDER`` value.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.auth.base import AuthProvider
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_auth_provider() -> AuthProvider:
    """
    Return the active auth provider.

    Reads ``settings.auth_provider`` and constructs the matching provider.
    Cached so only one instance exists per process.
    """
    settings = get_settings()
    choice = settings.auth_provider.lower().strip()

    if choice == "jwt":
        from app.auth.providers.jwt import JWTProvider

        provider: AuthProvider = JWTProvider()

    elif choice == "auth0":
        from app.auth.providers.auth0 import Auth0Provider

        provider = Auth0Provider()

    elif choice == "mock":
        from app.auth.providers.mock import MockProvider

        provider = MockProvider()

    else:
        raise AuthenticationError(
            f"Unknown AUTH_PROVIDER: {choice!r}. " "Expected one of: jwt, auth0, mock."
        )

    logger.info("Auth provider initialised: %s", provider.name)
    return provider
