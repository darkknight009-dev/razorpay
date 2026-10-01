from __future__ import annotations

import pytest

from connector.config import Settings
from connector.errors import ConfigurationError


def test_mock_mode_does_not_require_credentials() -> None:
    Settings(mock_mode=True).require_live_credentials()


def test_live_mode_requires_domain_and_key() -> None:
    with pytest.raises(ConfigurationError, match="FRESHDESK_DOMAIN"):
        Settings(mock_mode=False).require_live_credentials()


def test_live_mode_rejects_non_freshdesk_domain() -> None:
    with pytest.raises(ConfigurationError, match="Freshdesk host"):
        Settings(mock_mode=False, domain="example.test", api_key="test-only-key").require_live_credentials()


def test_live_mode_accepts_test_configuration() -> None:
    settings = Settings(
        mock_mode=False,
        domain="demo-shop.freshdesk.com",
        api_key="test-only-key",
    )
    settings.require_live_credentials()
    assert settings.base_url == "https://demo-shop.freshdesk.com/api/v2"
