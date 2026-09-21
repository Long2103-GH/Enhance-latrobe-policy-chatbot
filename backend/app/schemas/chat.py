"""Chat API schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.policy import PolicyCitation


class ChatMessage(BaseModel):
    """A previous conversation message."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=5000)


class ChatRequest(BaseModel):
    """Incoming chatbot question."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    conversation: list[ChatMessage] = Field(
        default_factory=list,
        max_length=8,
    )
    # Optional: attach this exchange to a persisted conversation.
    # If None, the backend creates a new conversation automatically.
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    """Safe chatbot response."""

    answer: str
    citations: list[PolicyCitation]
    grounded: bool
    confidence: float
    escalation_required: bool
    disclaimer: str
    request_id: str
    # The conversation this exchange was saved to (may be newly created).
    conversation_id: int | None = None
