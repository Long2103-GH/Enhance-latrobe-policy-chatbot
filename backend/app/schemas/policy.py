"""Policy-related API schemas."""

from pydantic import BaseModel, ConfigDict, HttpUrl


class PolicyCitation(BaseModel):
    """Citation returned to the frontend."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str
    policy_id: str
    title: str
    section: str
    url: HttpUrl


class RetrievedPolicyChunk(BaseModel):
    """Internal retrieval result (not currently used)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    policy_id: str
    title: str
    section: str
    text: str
    url: str
    score: float
