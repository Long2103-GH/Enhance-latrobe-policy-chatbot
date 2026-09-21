"""Authentication API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Password complexity
# ---------------------------------------------------------------------------


def _validate_password_strength(value: str) -> str:
    """
    Enforce production password rules:

      - At least 12 characters
      - At least one uppercase letter
      - At least one lowercase letter
      - At least one digit
      - At least one non-alphanumeric character
    """
    if len(value) < 12:
        raise ValueError("Password must be at least 12 characters long.")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in value):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one digit.")
    if not any(not c.isalnum() for c in value):
        raise ValueError("Password must contain at least one symbol.")
    return value


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Login credentials."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """JWT token response."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# User representation
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """
    Public user representation.

    Excludes sensitive fields (password_hash). Fields added for the
    IAM model are optional so older clients that don't expect them
    continue to work.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    email: EmailStr
    full_name: str
    role: str
    institutional_id: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    last_login_at: datetime | None = None


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------


class ChangePasswordRequest(BaseModel):
    """Payload to change a user's password."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class ChangePasswordResponse(BaseModel):
    """Confirmation that the password was changed."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------


class ForgotPasswordRequest(BaseModel):
    """Request a password reset."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Reset instructions returned to the user."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    support_email: str | None = None
    support_url: str | None = None
