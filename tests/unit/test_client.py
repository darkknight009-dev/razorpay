from __future__ import annotations

import base64

import httpx
import pytest

from connector.client import FreshdeskClient
from connector.config import Settings
from connector.errors import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
    UpstreamError,
)
from connector.models import GetTicketRequest, ListTicketsRequest, SearchTicketsRequest


def live_settings(**overrides: object) -> Settings:
    values = {
        "mock_mode": False,
        "domain": "test-shop.freshdesk.com",
        "api_key": "test-only-key",
        "max_retries": 2,
        "retry_base_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def ticket_payload(ticket_id: int = 10001) -> dict[str, object]:
    return {
        "id": ticket_id,
        "subject": "Fictional ticket",
        "status": 2,
        "priority": 3,
        "requester_id": 1,
        "tags": ["demo"],
        "description_text": "Fictional content only.",
        "created_at": "2026-09-30T10:00:00Z",
        "updated_at": "2026-09-30T10:01:00Z",
    }


@pytest.mark.asyncio
async def test_client_uses_basic_auth_and_normalizes_list() -> None:
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            200,
            json=[ticket_payload()],
            headers={"link": '<https://test-shop.freshdesk.com/api/v2/tickets?page=2>; rel="next"'},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = FreshdeskClient(live_settings(), http_client=http_client)
        result = await client.list_tickets(ListTicketsRequest(per_page=20))

    expected = "Basic " + base64.b64encode(b"test-only-key:X").decode()
    assert observed[0].headers["authorization"] == expected
    assert result.items[0].id == 10001
    assert result.pagination.next_page == 2


@pytest.mark.asyncio
async def test_client_get_and_search_use_documented_paths() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/search/tickets"):
            return httpx.Response(200, json={"total": 1, "results": [ticket_payload()]}, request=request)
        return httpx.Response(200, json=ticket_payload(), request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = FreshdeskClient(live_settings(), http_client=http_client)
        ticket = await client.get_ticket(GetTicketRequest(ticket_id=10001))
        search = await client.search_tickets(SearchTicketsRequest(query="status:2"))

    assert ticket.id == 10001
    assert search.total == 1
    assert paths == ["/api/v2/tickets/10001", "/api/v2/search/tickets"]


@pytest.mark.asyncio
async def test_client_honors_retry_after_and_succeeds() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0.25"}, json={"description": "limited"}, request=request)
        return httpx.Response(200, json=ticket_payload(), request=request)

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = FreshdeskClient(live_settings(), http_client=http_client, sleep=sleep)
        result = await client.get_ticket(GetTicketRequest(ticket_id=10001))

    assert result.id == 10001
    assert attempts == 2
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_client_rate_limit_exhaustion_is_bounded() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={}, request=request)

    async def sleep(_: float) -> None:
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = FreshdeskClient(live_settings(max_retries=2), http_client=http_client, sleep=sleep)
        with pytest.raises(RateLimitError) as error:
            await client.get_ticket(GetTicketRequest(ticket_id=10001))

    assert attempts == 3
    assert error.value.status_code == 429


@pytest.mark.asyncio
async def test_client_maps_auth_timeout_and_upstream_errors() -> None:
    async def auth_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"description": "invalid_credentials"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(auth_handler)) as http_client:
        client = FreshdeskClient(live_settings(max_retries=0), http_client=http_client)
        with pytest.raises(AuthenticationError) as error:
            await client.get_ticket(GetTicketRequest(ticket_id=10001))
    assert "test-only-key" not in str(error.value)

    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as http_client:
        client = FreshdeskClient(live_settings(max_retries=0), http_client=http_client)
        with pytest.raises(NetworkError, match="timed out"):
            await client.get_ticket(GetTicketRequest(ticket_id=10001))

    async def server_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"description": "server problem"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(server_handler)) as http_client:
        client = FreshdeskClient(live_settings(max_retries=0), http_client=http_client)
        with pytest.raises(UpstreamError, match="temporary server error"):
            await client.get_ticket(GetTicketRequest(ticket_id=10001))
