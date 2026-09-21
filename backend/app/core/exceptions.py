"""Application-specific exceptions."""

from typing import Any


class ApplicationError(Exception):
    """Base application exception."""

    status_code: int = 500
    error_code: str = "APPLICATION_ERROR"
    default_public_message: str = (
        "Something went wrong while processing your request. "
        "Please try again or contact support with the reference provided."
    )

    def __init__(
        self,
        message: str,
        *,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.public_message = self.default_public_message
        self.details = details


class AuthenticationError(ApplicationError):
    """Raised when authentication fails."""

    status_code = 401
    error_code = "AUTHENTICATION_ERROR"
    default_public_message = "Your session is invalid or expired. Please log in again."


class AuthorizationError(ApplicationError):
    """Raised when authorization fails."""

    status_code = 403
    error_code = "AUTHORIZATION_ERROR"
    default_public_message = "You do not have permission to perform this action."


class ValidationError(ApplicationError):
    """Raised for domain-level validation failures."""

    status_code = 422
    error_code = "VALIDATION_ERROR"
    default_public_message = "The request could not be processed due to invalid input."


class RetrievalError(ApplicationError):
    """Raised when policy retrieval fails."""

    status_code = 503
    error_code = "RETRIEVAL_ERROR"
    default_public_message = (
        "The policy search service is temporarily unavailable. "
        "Please try again in a moment."
    )


class GenerationError(ApplicationError):
    """Raised when LLM generation fails."""

    status_code = 503
    error_code = "GENERATION_ERROR"
    default_public_message = (
        "The answer generation service is temporarily unavailable. "
        "Please try again in a moment."
    )


class GroundingError(ApplicationError):
    """Raised when generated content cannot be safely grounded."""

    status_code = 422
    error_code = "GROUNDING_ERROR"
    default_public_message = (
        "The system could not produce a reliably grounded answer for your question. "
        "Please rephrase, or contact the relevant university office for guidance."
    )
