"""Authentication provider interface.

Every auth provider (JWT, Auth0, mock) implements this same interface.
The rest of the app never talks to a provider directly — it goes through
the factory in ``app.auth.factory``, which returns the active provider
based on the ``AUTH_PROVIDER`` setting.

This keeps the switch between local JWT (development) and university SSO
(production) to a single environment variable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Authenticated user shape
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CurrentUser:
    """
    The authenticated user, as seen by the rest of the app.

    Providers convert their internal representation (JWT claims, Auth0
    token, etc.) into this shape. Routes and services only ever see
    ``CurrentUser`` — they never know which provider authenticated them.
    """

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool = True


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


class AuthProvider(ABC):
    """
    Base class for authentication providers.

    All methods are async because real providers make network calls
    (JWKS fetch, token introspection). Implementations that don't need
    the network (like the mock provider) still implement the same
    signatures so the interface is uniform.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier — matches the ``AUTH_PROVIDER`` setting."""
        ...

    @property
    def supports_password_change(self) -> bool:
        """
        Whether this provider allows changing passwords locally.

        JWT providers return True; Auth0 and mock return False
        (Auth0 manages passwords on its own hosted pages).
        """
        return False

    @abstractmethod
    async def authenticate(
        self,
        session: AsyncSession,
        email: str,
        password: str,
    ) -> str:
        """
        Exchange credentials for a token.

        Returns: the token string to send back to the client.

        Raises: ``AuthenticationError`` if credentials are invalid.
        """
        ...

    @abstractmethod
    async def verify_token(
        self,
        session: AsyncSession,
        token: str,
    ) -> CurrentUser:
        """
        Verify a token and return the authenticated user.

        Raises: ``AuthenticationError`` if the token is invalid or expired.
        """
        ...

    @abstractmethod
    async def logout(self, token: str) -> None:
        """
        Revoke a token, if the provider supports it.

        For stateless providers (JWT, Auth0 access tokens), this is a
        no-op — the client simply discards the token.
        """
        ...

    async def change_password(
        self,
        session: AsyncSession,
        user: CurrentUser,
        current_password: str,
        new_password: str,
    ) -> None:
        """
        Change the user's password.

        Default implementation raises — providers that support this
        override the method. Callers should check
        ``supports_password_change`` before invoking.
        """
        raise NotImplementedError(
            f"Password change is not supported by the '{self.name}' provider."
        )
