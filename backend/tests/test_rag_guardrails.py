"""RAG safety and guardrail tests.

Covers:
  - Sensitive domain behavior (financial, legal, medical)
  - Fallback path (no evidence)
  - Grounding failure path
  - Cross-user conversation isolation
"""

import pytest

# ────────────────────────────────────────────────────────────────────────
# Conversation ownership (cross-user isolation)
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversations_are_user_scoped(
    test_client, db_session, student_token, admin_token
):
    """A user can only see their own conversations."""
    from app.db.models import User, Conversation
    from sqlalchemy import select

    student = (
        await db_session.execute(select(User).where(User.email == "student@test.edu"))
    ).scalar_one()
    admin = (
        await db_session.execute(select(User).where(User.email == "admin@test.edu"))
    ).scalar_one()

    conv = Conversation(user_id=student.id, title="Student's private conversation")
    db_session.add(conv)
    await db_session.flush()
    await db_session.commit()

    resp_student = await test_client.get(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp_student.status_code == 200
    student_ids = [c["id"] for c in resp_student.json()["conversations"]]
    assert conv.id in student_ids

    resp_admin = await test_client.get(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_admin.status_code == 200
    admin_ids = [c["id"] for c in resp_admin.json()["conversations"]]
    assert conv.id not in admin_ids


@pytest.mark.asyncio
async def test_admin_cannot_read_other_users_conversation(
    test_client, db_session, student_token, admin_token
):
    """Even with a valid id, another user gets 404."""
    from app.db.models import User, Conversation
    from sqlalchemy import select

    student = (
        await db_session.execute(select(User).where(User.email == "student@test.edu"))
    ).scalar_one()

    conv = Conversation(user_id=student.id, title="Private")
    db_session.add(conv)
    await db_session.flush()
    await db_session.commit()

    response = await test_client.get(
        f"/api/v1/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_cannot_delete_other_users_conversation(
    test_client, db_session, student_token, admin_token
):
    """Delete on someone else's conversation returns 404 and does not delete."""
    from app.db.models import User, Conversation
    from sqlalchemy import select

    student = (
        await db_session.execute(select(User).where(User.email == "student@test.edu"))
    ).scalar_one()

    conv = Conversation(user_id=student.id, title="Private")
    db_session.add(conv)
    await db_session.flush()
    await db_session.commit()

    response = await test_client.delete(
        f"/api/v1/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404

    response = await test_client.get(
        f"/api/v1/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert response.status_code == 200


# ────────────────────────────────────────────────────────────────────────
# Chat: authentication required
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_requires_authentication(test_client):
    """Unauthenticated chat requests → 401."""
    response = await test_client.post(
        "/api/v1/chat",
        json={"query": "Hi", "conversation": [], "conversation_id": None},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_rejects_empty_query(test_client, student_token):
    """Empty query → 422."""
    response = await test_client.post(
        "/api/v1/chat",
        json={"query": "", "conversation": [], "conversation_id": None},
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_oversized_query(test_client, student_token):
    """Query above 2000 chars → 422."""
    response = await test_client.post(
        "/api/v1/chat",
        json={"query": "x" * 2001, "conversation": [], "conversation_id": None},
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 422


# ────────────────────────────────────────────────────────────────────────
# Chat: successful path (with all external services mocked)
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_returns_grounded_answer(
    test_client,
    student_token,
    mock_embedding_service,
    mock_vector_store,
    mock_lexical_store,
    mock_generation_service,
):
    """A well-formed chat returns a grounded answer with citations."""
    mock_vector_store["c1"] = {
        "vector": [0.1] * 1024,
        "payload": {
            "chunk_id": "c1",
            "policy_id": "policy-1",
            "title": "Return Policy",
            "url": "https://example.test/policy/return",
            "section": "Returns",
            "text": "You can return electronics within 30 days.",
            "chunk_index": 0,
        },
    }

    mock_generation_service.response = "You can return electronics within 30 days [C1]."

    response = await test_client.post(
        "/api/v1/chat",
        json={
            "query": "How do I return electronics?",
            "conversation": [],
            "conversation_id": None,
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert body["conversation_id"] is not None
    assert len(body["citations"]) >= 1
    assert body["citations"][0]["citation_id"] == "C1"


# ────────────────────────────────────────────────────────────────────────
# Chat: no evidence path
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_with_no_retrieved_evidence_uses_fallback(
    test_client,
    student_token,
    mock_embedding_service,
    mock_vector_store,
    mock_lexical_store,
    mock_generation_service,
):
    """Empty stores → fallback response, not grounded."""
    response = await test_client.post(
        "/api/v1/chat",
        json={
            "query": "What's the meaning of life?",
            "conversation": [],
            "conversation_id": None,
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["confidence"] == 0.0
    assert body["escalation_required"] is True
    answer_lower = body["answer"].lower()
    assert "couldn't find" in answer_lower or "could not find" in answer_lower


# ────────────────────────────────────────────────────────────────────────
# Chat: grounding failure path
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_with_invalid_citations_returns_safe_error(
    test_client,
    student_token,
    mock_embedding_service,
    mock_vector_store,
    mock_lexical_store,
    mock_generation_service,
):
    """
    LLM cites [C99] (invalid) → pipeline treats it as a grounding failure
    and returns a safe error message (not a raw exception).
    """
    mock_vector_store["c1"] = {
        "vector": [0.1] * 1024,
        "payload": {
            "chunk_id": "c1",
            "policy_id": "policy-1",
            "title": "T",
            "url": "https://example.test",
            "section": "S",
            "text": "Real evidence text",
            "chunk_index": 0,
        },
    }

    mock_generation_service.response = "Some answer with a fake [C99] citation."

    response = await test_client.post(
        "/api/v1/chat",
        json={
            "query": "Tell me something",
            "conversation": [],
            "conversation_id": None,
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["escalation_required"] is True
    assert "Traceback" not in body["answer"]
    assert "GroundingError" not in body["answer"]


# ────────────────────────────────────────────────────────────────────────
# Query rewriting: only fires for follow-ups
# ────────────────────────────────────────────────────────────────────────


def test_query_rewrite_skipped_for_first_turn():
    from app.services.query_rewriter import needs_rewrite

    assert needs_rewrite("How do I return electronics?", []) is False


def test_query_rewrite_skipped_for_self_contained_followup():
    from app.services.query_rewriter import needs_rewrite
    from app.schemas.chat import ChatMessage

    conversation = [
        ChatMessage(role="user", content="First question"),
        ChatMessage(role="assistant", content="First answer"),
    ]
    assert (
        needs_rewrite(
            "What is the maximum leave duration for graduate research candidates?",
            conversation,
        )
        is False
    )


def test_query_rewrite_fires_for_pronoun_followup():
    from app.services.query_rewriter import needs_rewrite
    from app.schemas.chat import ChatMessage

    conversation = [
        ChatMessage(role="user", content="Tell me about the scholarship."),
        ChatMessage(role="assistant", content="Here is what the policy says..."),
    ]

    assert needs_rewrite("So how do I get that?", conversation) is True


def test_query_rewrite_fires_for_vague_short_followup():
    from app.services.query_rewriter import needs_rewrite
    from app.schemas.chat import ChatMessage

    conversation = [
        ChatMessage(role="user", content="What is the leave policy?"),
        ChatMessage(role="assistant", content="The leave policy says..."),
    ]

    assert needs_rewrite("Tell me more", conversation) is True
