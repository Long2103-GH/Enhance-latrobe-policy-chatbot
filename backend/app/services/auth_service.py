"""Authentication service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    verify_password,
)
from app.db.repositories import UserRepository


class AuthService:
    """Authenticate application users and issue JWT tokens."""

    async def authenticate(
        self,
        session: AsyncSession,
        email: str,
        password: str,
    ) -> str:
        """Authenticate user credentials and issue a signed JWT access token.

        Args:
            session: Active asynchronous database session.
            email: User email address input.
            password: Plaintext password input.

        Returns:
            Encoded JWT access token string.

        Raises:
            AuthenticationError: If credentials are invalid or account is inactive.
        """
        if not email or not password:
            raise AuthenticationError("Invalid email or password.")

        normalized_email = email.lower().strip()
        users_repo = UserRepository(session)

        # Streamline query using the repository cleanly (avoiding duplicate lookups)
        user = await users_repo.get_by_email(normalized_email)

        if user is None:
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationError("This account is inactive.")

        if not verify_password(
            password,
            user.password_hash,
        ):
            raise AuthenticationError("Invalid email or password.")

        return create_access_token(
            str(user.id),
            role=user.role,
        )
