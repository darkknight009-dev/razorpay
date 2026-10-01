"""Safe, agent-facing connector errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ConnectorError(Exception):
    """Base error with a safe message suitable for an MCP tool result."""

    message: str
    code: str = "connector_error"
    retry_after: float | None = None
    status_code: int | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def public_message(self) -> str:
        suffix = f" Retry after {self.retry_after:g} seconds." if self.retry_after else ""
        return f"{self.message}{suffix}"


class ConfigurationError(ConnectorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration_error")


class ValidationError(ConnectorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="validation_error", status_code=400)


class AuthenticationError(ConnectorError):
    def __init__(self) -> None:
        super().__init__(
            "Freshdesk rejected the credentials. Verify FRESHDESK_DOMAIN and the API key.",
            code="authentication_error",
            status_code=401,
        )


class PermissionDeniedError(ConnectorError):
    def __init__(self) -> None:
        super().__init__(
            "The Freshdesk identity is not allowed to read this resource.",
            code="permission_denied",
            status_code=403,
        )


class NotFoundError(ConnectorError):
    def __init__(self, resource: str = "resource") -> None:
        super().__init__(
            f"Freshdesk {resource} was not found.", code="not_found", status_code=404
        )


class BadRequestError(ConnectorError):
    def __init__(self, message: str = "Freshdesk rejected the request.") -> None:
        super().__init__(message, code="bad_request", status_code=400)


class RateLimitError(ConnectorError):
    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__(
            "Freshdesk rate limit reached after the connector's bounded retries.",
            code="rate_limited",
            retry_after=retry_after,
            status_code=429,
        )


class NetworkError(ConnectorError):
    def __init__(self, message: str = "Freshdesk could not be reached.") -> None:
        super().__init__(message, code="network_error")


class UpstreamError(ConnectorError):
    def __init__(self, message: str = "Freshdesk returned an unusable response.", status_code: int | None = None) -> None:
        super().__init__(message, code="upstream_error", status_code=status_code)


def safe_upstream_message(payload: Any) -> str:
    """Extract a short, non-sensitive message from a Freshdesk error body."""

    if not isinstance(payload, dict):
        return "Freshdesk rejected the request."
    description = payload.get("description")
    if isinstance(description, str) and description.strip():
        return description.strip()[:300]
    errors = payload.get("errors")
    if isinstance(errors, list):
        messages: list[str] = []
        for item in errors[:3]:
            if isinstance(item, dict):
                message = item.get("message")
                if isinstance(message, str) and message.strip():
                    messages.append(message.strip()[:180])
        if messages:
            return "; ".join(messages)
    return "Freshdesk rejected the request."
