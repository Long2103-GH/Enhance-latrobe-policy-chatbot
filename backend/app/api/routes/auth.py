"""Authentication endpoints."""

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.auth.base import CurrentUser
from app.auth.factory import get_auth_provider
from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.core.rate_limit import limiter
from app.db.database import get_db
from app.db.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ---------------------------------------------------------------------------
# Login / identity
# ---------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate a user."""
    provider = get_auth_provider()
    token = await provider.authenticate(
        session,
        payload.email,
        payload.password,
    )

    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=UserResponse,
)
async def me(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Return the current authenticated user."""
    result = await session.execute(select(User).where(User.id == current_user.id))
    db_user = result.scalar_one_or_none()

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        institutional_id=db_user.institutional_id if db_user else None,
        is_active=current_user.is_active,
        created_at=db_user.created_at if db_user else None,
        last_login_at=db_user.last_login_at if db_user else None,
    )


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------


@router.post(
    "/change-password",
    response_model=ChangePasswordResponse,
)
@limiter.limit("3/minute")
async def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChangePasswordResponse:
    """
    Change the current user's password.

    Only supported by providers that manage passwords locally (JWT).
    Auth0 users must change their password through the Auth0-hosted
    page instead.
    """
    provider = get_auth_provider()

    if not provider.supports_password_change:
        raise ValidationError(
            f"Password change is not available for the "
            f"'{provider.name}' sign-in method. "
            "Please use the university's password management page."
        )

    await provider.change_password(
        session,
        current_user,
        payload.current_password,
        payload.new_password,
    )

    return ChangePasswordResponse(
        success=True,
        message="Your password has been updated.",
    )


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    response: Response,
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    """
    Password reset information.

    This deployment does NOT manage password resets directly — that is
    handled by La Trobe's IT support and identity services. This endpoint
    exists so the frontend can route users to the right place without
    leaking whether an account exists.

    Returns the same message for every email, existing or not, to prevent
    account enumeration.
    """
    settings = get_settings()

    logger.info("Password reset requested for %s", payload.email)

    return ForgotPasswordResponse(
        success=True,
        message=(
            "Password resets are handled by La Trobe IT Support. "
            "Please contact them with your student or staff ID."
        ),
        support_email=settings.support_email,
        support_url=settings.support_url,
    )
