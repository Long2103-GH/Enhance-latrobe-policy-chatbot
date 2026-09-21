"""Auth0 authentication provider.

Verifies RS256-signed JWTs issued by Auth0 using the tenant's JWKS
endpoint. On first successful verification, the user is created (or
updated) in our local database so the rest of the app has a stable
internal user id.

Design notes:
  - The Auth0 ``sub`` claim (e.g. ``auth0|abc123``) is the stable
    external identifier. We store it in the ``external_id`` column.
  - Only emails ending in the configured allowed domain are accepted.
    This is a second-layer check on top of the Auth0 Action that
    already restricts signups to that domain.
  - JWKS is cached in-process for a short period to avoid a network
    call on every request.
"""

from __future__ import annotations

import logging
import time

import httpx
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthProvider, CurrentUser
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.db.models import User

logger = logging.getLogger(__name__)


# JWKS cache: a small in-process cache with a TTL so we don't hit the
# Auth0 endpoint on every request. Ten minutes is standard.
_JWKS_TTL_SECONDS = 600
_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


class Auth0Provider(AuthProvider):
    """Verify Auth0-issued JWTs and mirror users into our database."""

    def __init__(self) -> None:
        settings = get_settings()
        self.domain = settings.auth0_domain
        self.audience = settings.auth0_audience
        self.issuer = settings.auth0_issuer
        self.allowed_domain = settings.auth0_allowed_domain.lower()

        if (
            not self.domain
            or not self.audience
            or not self.issuer
            or not self.allowed_domain
            ):
                raise AuthenticationError(
                    "Auth0 provider selected but AUTH0_DOMAIN, AUTH0_AUDIENCE, "
                    "AUTH0_ISSUER or AUTH0_ALLOWED_DOMAIN is not configured."
                )

    @property
    def name(self) -> str:
        return "auth0"

    # ------------------------------------------------------------------
    # Authenticate is not supported by this provider
    # ------------------------------------------------------------------

    async def authenticate(
        self,
        session: AsyncSession,
        email: str,
        password: str,
    ) -> str:
        """
        Auth0 uses redirect-based login, not credential exchange.

        The front end redirects the user to the Auth0 Universal Login
        page; Auth0 returns a token to the browser. We never see the
        user's password. So this method is not applicable.
        """
        raise AuthenticationError(
            "Auth0 uses redirect login. "
            "The client should call /auth/login-url instead."
        )

    # ------------------------------------------------------------------
    # Verify an Auth0 token
    # ------------------------------------------------------------------

    async def verify_token(
        self,
        session: AsyncSession,
        token: str,
    ) -> CurrentUser:
        payload = await self._decode_token(token)

        email = payload.get("email")
        if not email:
            raise AuthenticationError(
                "Auth0 token does not contain an email claim. "
                "Ensure the 'email' scope is requested at login."
            )

        email = email.lower().strip()
        if not email.endswith("@" + self.allowed_domain):
            raise AuthenticationError(
                f"Only @{self.allowed_domain} accounts are allowed."
            )

        external_id = payload.get("sub")
        if not external_id:
            raise AuthenticationError("Auth0 token does not contain a subject claim.")

        full_name = payload.get("name") or self._name_from_email(email)
        user = await self._upsert_user(session, external_id, email, full_name)

        return CurrentUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        )

    async def logout(self, token: str) -> None:
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _decode_token(self, token: str) -> dict:
        jwks = await self._get_jwks()
        try:
            return jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
            )
        except JWTError as exc:
            logger.warning("Auth0 token verification failed: %s", exc)
            raise AuthenticationError("Invalid or expired Auth0 token.") from exc

    async def _get_jwks(self) -> dict:
        now = time.time()
        if (
            _jwks_cache["keys"] is not None
            and now - _jwks_cache["fetched_at"] < _JWKS_TTL_SECONDS
        ):
            return _jwks_cache["keys"]

        url = f"https://{self.domain}/.well-known/jwks.json"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                jwks = response.json()
        except httpx.HTTPError as exc:
            logger.exception("Failed to fetch Auth0 JWKS from %s", url)
            raise AuthenticationError(
                "Could not reach the authentication service."
            ) from exc

        _jwks_cache["keys"] = jwks
        _jwks_cache["fetched_at"] = now
        return jwks

    async def _upsert_user(
        self,
        session: AsyncSession,
        external_id: str,
        email: str,
        full_name: str,
    ) -> User:
        result = await session.execute(
            select(User).where(User.external_id == external_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                external_id=external_id,
                email=email,
                full_name=full_name,
                password_hash="",  # Auth0 users have no local password
                role="student",
                is_active=True,
            )
            session.add(user)
            await session.flush()
            await session.commit()
            logger.info("Created local user for Auth0 sub=%s", external_id)
        else:
            changed = False
            if user.email != email:
                user.email = email
                changed = True
            if user.full_name != full_name:
                user.full_name = full_name
                changed = True
            if changed:
                await session.flush()
                await session.commit()

        return user

    @staticmethod
    def _name_from_email(email: str) -> str:
        local = email.split("@")[0]
        parts = [p.capitalize() for p in local.split(".") if p]
        if not parts:
            return email
        if len(parts) == 1:
            return parts[0]
        return " ".join(f"{p[0]}." for p in parts[:-1]) + " " + parts[-1]
