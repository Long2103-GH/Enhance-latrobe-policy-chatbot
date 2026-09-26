"""Authentication endpoint tests."""

from datetime import UTC

import pytest

# ────────────────────────────────────────────────────────────────────────
# POST /auth/login — success cases
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_returns_jwt_for_valid_credentials(test_client, seeded_user):
    """Correct email + password returns a JWT."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": seeded_user["email"], "password": seeded_user["password"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


@pytest.mark.asyncio
async def test_login_email_is_case_insensitive(test_client, seeded_user):
    """Uppercase emails still log in."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": seeded_user["email"].upper(),
            "password": seeded_user["password"],
        },
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_email_is_trimmed(test_client, seeded_user):
    """Whitespace around the email is stripped."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "email": f"  {seeded_user['email']}  ",
            "password": seeded_user["password"],
        },
    )

    assert response.status_code == 200


# ────────────────────────────────────────────────────────────────────────
# POST /auth/login — failure cases
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(test_client, seeded_user):
    """Wrong password → 401."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": seeded_user["email"], "password": "WrongPassword!"},
    )

    assert response.status_code == 401
    assert "invalid" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(test_client):
    """Unknown email → 401 (same message as wrong password)."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.edu", "password": "Password123!"},
    )

    assert response.status_code == 401
    assert "invalid" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401(test_client, db_session):
    """Inactive users cannot log in."""
    from app.core.security import hash_password
    from app.db.models import User

    user = User(
        email="inactive@test.edu",
        full_name="Inactive",
        password_hash=hash_password("Password123!"),
        role="student",
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@test.edu", "password": "Password123!"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_invalid_email_format_returns_422(test_client):
    """Malformed email → validation error."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "Password123!"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_short_password_returns_401(test_client, seeded_user):
    """
    Wrong-length passwords are treated identically to any other wrong
    credentials — 401, not 422.

    Telling the client "your password is the wrong length" is an
    information leak. Login endpoints must not distinguish.
    """
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": seeded_user["email"], "password": "short"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_missing_fields_returns_422(test_client):
    """Missing required fields → validation error."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "someone@test.edu"},
    )

    assert response.status_code == 422


# ────────────────────────────────────────────────────────────────────────
# GET /auth/me
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_returns_user_info_with_valid_token(
    test_client, student_token, seeded_user
):
    """Valid JWT → current user info."""
    response = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == seeded_user["id"]
    assert body["email"] == seeded_user["email"]
    assert body["role"] == seeded_user["role"]
    assert "password_hash" not in body
    assert "password" not in body


@pytest.mark.asyncio
async def test_me_without_token_returns_401(test_client):
    """No Authorization header → 401."""
    response = await test_client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_malformed_token_returns_401(test_client):
    """Garbage token → 401."""
    response = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_expired_token_returns_401(test_client, seeded_user):
    """Expired JWT → 401."""
    from datetime import datetime, timedelta

    from jose import jwt

    from app.core.config import get_settings

    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": str(seeded_user["id"]),
            "role": seeded_user["role"],
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "iat": datetime.now(UTC) - timedelta(hours=2),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_inactive_user_returns_401(test_client, db_session):
    """A valid token for a user that was deactivated → 401."""
    from app.core.security import create_access_token, hash_password
    from app.db.models import User

    user = User(
        email="will-deactivate@test.edu",
        full_name="Soon Inactive",
        password_hash=hash_password("Password123!"),
        role="student",
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    token = create_access_token(str(user.id), role=user.role)

    response = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


# ────────────────────────────────────────────────────────────────────────
# Admin-only access
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_endpoint_forbidden_for_student(
    test_client,
    student_token,
    mock_embedding_service,
    mock_vector_store,
    mock_lexical_store,
):
    """A student token cannot access admin-only endpoints."""
    response = await test_client.post(
        "/api/v1/admin/reindex",
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 403
