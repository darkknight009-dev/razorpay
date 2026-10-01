"""Environment-backed application configuration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

from .errors import ConfigurationError

_DOMAIN_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.freshdesk\.com$")


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError("MOCK_MODE must be true or false.")


def _float(name: str, value: str | None, default: float, minimum: float = 0.0, min_value: float | None = None) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if parsed < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}.")
    if min_value is not None and parsed < min_value:
        raise ConfigurationError(f"{name} must be at least {min_value}.")
    return parsed


def _int(name: str, value: str | None, default: int, minimum: int = 0, min_value: int | None = None) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if parsed < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}.")
    return parsed


@dataclass(frozen=True)
class Settings:
    mock_mode: bool = True
    domain: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_base_seconds: float = 0.25
    request_spacing_seconds: float = 0.0
    max_list_pages: int = 10
    max_list_results: int = 1000

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        return cls(
            mock_mode=_bool(os.getenv("MOCK_MODE"), True),
            domain=os.getenv("FRESHDESK_DOMAIN") or None,
            api_key=os.getenv("FRESHDESK_API_KEY") or None,
            timeout_seconds=_float("FRESHDESK_TIMEOUT_SECONDS", os.getenv("FRESHDESK_TIMEOUT_SECONDS"), 10.0, min_value=0.1),
            max_retries=_int("FRESHDESK_MAX_RETRIES", os.getenv("FRESHDESK_MAX_RETRIES"), 2, 0),
            retry_base_seconds=_float("FRESHDESK_RETRY_BASE_SECONDS", os.getenv("FRESHDESK_RETRY_BASE_SECONDS"), 0.25, min_value=0.0),
            request_spacing_seconds=_float("FRESHDESK_REQUEST_SPACING_SECONDS", os.getenv("FRESHDESK_REQUEST_SPACING_SECONDS"), 0.0, min_value=0.0),
            max_list_pages=_int("FRESHDESK_MAX_LIST_PAGES", os.getenv("FRESHDESK_MAX_LIST_PAGES"), 10, min_value=1),
            max_list_results=_int("FRESHDESK_MAX_LIST_RESULTS", os.getenv("FRESHDESK_MAX_LIST_RESULTS"), 1000, min_value=1),
        )

    @property
    def base_url(self) -> str:
        self.require_live_credentials()
        assert self.domain is not None
        return f"https://{self.domain}/api/v2"

    def require_live_credentials(self) -> None:
        if self.mock_mode:
            return
        if not self.domain:
            raise ConfigurationError("FRESHDESK_DOMAIN is required when MOCK_MODE=false.")
        normalized = self.domain.strip().lower()
        if not _DOMAIN_PATTERN.fullmatch(normalized):
            raise ConfigurationError(
                "FRESHDESK_DOMAIN must be a Freshdesk host such as your-subdomain.freshdesk.com."
            )
        if not self.api_key:
            raise ConfigurationError("FRESHDESK_API_KEY is required when MOCK_MODE=false.")
        if any(char.isspace() for char in self.api_key):
            raise ConfigurationError("FRESHDESK_API_KEY must not contain whitespace.")
