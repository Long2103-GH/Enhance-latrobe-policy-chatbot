"""Mock authentication provider — for tests only.

Returns a fixed user without touching the database or the network.
Selected when ``AUTH_PROVIDER=mock`` in the environment.

This provider exists so test suites can run without real credentials,
real tokens, or a real database. It must NEVER be enabled in production.

WARNING: The mock user's ``id`` (999999) does not exist in the database.
Any endpoint that writes a foreign key referencing ``users.id`` (e.g.
``/chat``, which persists conversations and audit events) will fail
unless the mock user is inserted into the DB first. Use only for tests
that don't write foreign-keyed rows, or seed the user in a fixture.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthProvider, CurrentUser
from app.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


# The user every mock request is authenticated as.
_MOCK_USER = CurrentUser(
    id=999999,
    email="test.user@test.edu",
    full_name="Test User",
    role="student",
    is_active=True,
)


class MockProvider(AuthProvider):
    """
    Returns a fixed user for the literal token "mock-token".

    Rules:
      - ``authenticate`` accepts any credentials and returns "mock-token".
      - ``verify_token`` returns the fixed user only for "mock-token".
      - Any other token raises ``AuthenticationError``.
    """

    @property
    def name(self) -> str:
        return "mock"

    async def authenticate(
        self,
        session: AsyncSession,
        email: str,
        password: str,
    ) -> str:
        logger.warning(
            "MockProvider.authenticate called — this should never "
            "happen in production. email=%r",
            email,
        )
        return "mock-token"

    async def verify_token(
        self,
        session: AsyncSession,
        token: str,
    ) -> CurrentUser:
        if token != "mock-token":
            raise AuthenticationError(
                "Mock provider only accepts the token 'mock-token'."
            )
        return _MOCK_USER

    async def logout(self, token: str) -> None:
        return None
