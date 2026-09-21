"""Common API schemas."""

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Standard API error response."""

    model_config = ConfigDict(extra="forbid")

    error: str
    message: str
    request_id: str
