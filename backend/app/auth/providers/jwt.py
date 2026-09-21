"""JWT authentication provider.

Wraps the Argon2 + JWT logic from ``app.core.security`` behind the
``AuthProvider`` interface. Users live in the local database; passwords
are hashed with Argon2id; tokens are HMAC-signed JWTs. No external
service is called.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthProvider, CurrentUser
from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.models import User

logger = logging.getLogger(__name__)


class JWTProvider(AuthProvider):
    """Local, self-contained authentication."""

    @property
    def name(self) -> str:
        return "jwt"

    @property
    def supports_password_change(self) -> bool:
        return True

    async def authenticate(
        self,
        session: AsyncSession,
        email: str,
        password: str,
    ) -> str:
        normalized = email.lower().strip()

        result = await session.execute(select(User).where(User.email == normalized))
        user = result.scalar_one_or_none()

        if user is None:
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationError("This account is inactive.")

        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")

        return create_access_token(str(user.id), role=user.role)

    async def verify_token(
        self,
        session: AsyncSession,
        token: str,
    ) -> CurrentUser:
        payload = decode_access_token(token)

        try:
            user_id = int(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("Invalid authentication subject.") from exc

        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None or not user.is_active:
            raise AuthenticationError(
                "Authenticated user does not exist or is inactive."
            )

        return CurrentUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        )

    async def logout(self, token: str) -> None:
        return None

    async def change_password(
        self,
        session: AsyncSession,
        user: CurrentUser,
        current_password: str,
        new_password: str,
    ) -> None:
        """
        Change the current user's password.

        Verifies the old password before writing the new hash. Raises
        AuthenticationError if the old password is wrong or the user
        no longer exists.
        """
        result = await session.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one_or_none()

        if db_user is None or not db_user.is_active:
            raise AuthenticationError("User account is not active.")

        if not verify_password(current_password, db_user.password_hash):
            raise AuthenticationError("Current password is incorrect.")

        if current_password == new_password:
            raise AuthenticationError("New password must differ from the current one.")

        db_user.password_hash = hash_password(new_password)
        await session.commit()
        logger.info("Password changed for user id=%s", user.id)
