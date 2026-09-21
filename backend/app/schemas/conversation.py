"""Conversation API schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.policy import PolicyCitation


class ConversationSummary(BaseModel):
    """Lightweight conversation record for list views."""

    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationMessageRecord(BaseModel):
    """A single stored message."""

    model_config = ConfigDict(extra="forbid")

    id: int
    role: str
    content: str
    citations: list[PolicyCitation] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(BaseModel):
    """Full conversation with messages."""

    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageRecord]


class ConversationCreateRequest(BaseModel):
    """Payload to create a new conversation."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)


class ConversationRenameRequest(BaseModel):
    """Payload to rename a conversation."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)


class ConversationListResponse(BaseModel):
    """Paginated conversation list."""

    model_config = ConfigDict(extra="forbid")

    conversations: list[ConversationSummary]
