"""Async Freshdesk API v2 client with bounded retries and normalization."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from .config import Settings
from .errors import (
    AuthenticationError,
    BadRequestError,
    ConfigurationError,
    ConnectorError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UpstreamError,
    safe_upstream_message,
)
from .models import (
    GetTicketRequest,
    ListTicketsRequest,
    PageInfo,
    SearchPage,
    SearchTicketsRequest,
    Ticket,
    TicketPage,
    normalize_ticket,
)
from .rate_limit import RateLimiter

Sleep = Callable[[float], Awaitable[None]]
_NEXT_LINK = re.compile(r"<([^>]+)>\s*;\s*rel=[\"']next[\"']", re.IGNORECASE)


class FreshdeskClient:
    """The only class allowed to make live Freshdesk HTTP requests."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
        limiter: RateLimiter | None = None,
    ) -> None:
        settings.require_live_credentials()
        if settings.mock_mode:
            raise ConfigurationError("FreshdeskClient cannot be used while MOCK_MODE=true.")
        self.settings = settings
        self._http = http_client or httpx.AsyncClient(timeout=settings.timeout_seconds)
        self._owns_http = http_client is None
        self._sleep = sleep
        self._limiter = limiter or RateLimiter(settings.request_spacing_seconds, sleep=sleep)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def list_tickets(self, request: ListTicketsRequest) -> TicketPage:
        params: dict[str, str | int] = {
            "page": request.page,
            "per_page": request.per_page,
            "order_by": request.order_by,
            "order_type": request.order_type,
        }
        if request.email:
            params["email"] = request.email
        if request.requester_id is not None:
            params["requester_id"] = request.requester_id
        if request.company_id is not None:
            params["company_id"] = request.company_id
        if request.updated_since:
            params["updated_since"] = request.updated_since
        if request.filter:
            params["filter"] = request.filter
        if request.include_description:
            params["include"] = "description"

        response = await self._request("/tickets", params=params)
        payload = self._json(response)
        if not isinstance(payload, list):
            raise UpstreamError("Freshdesk returned an invalid ticket list.", response.status_code)
        items = [normalize_ticket(item) for item in payload]
        next_page = self._next_page(response.headers.get("link"))
        return TicketPage(
            items=items,
            pagination=PageInfo(
                page=request.page,
                per_page=request.per_page,
                has_more=next_page is not None,
                next_page=next_page,
            ),
        )

    async def get_ticket(self, request: GetTicketRequest) -> Ticket:
        params: dict[str, str] = {}
        if request.include:
            params["include"] = ",".join(include.value for include in request.include)
        response = await self._request(f"/tickets/{request.ticket_id}", params=params)
        payload = self._json(response)
        try:
            return normalize_ticket(payload)
        except ConnectorError:
            raise
        except Exception as exc:
            raise UpstreamError("Freshdesk returned an invalid ticket.", response_status_code) from exc

    async def search_tickets(self, request: SearchTicketsRequest) -> SearchPage:
        response = await self._request(
            "/search/tickets",
            params={"query": request.query, "page": request.page},
        )
        payload = self._json(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise UpstreamError("Freshdesk returned an invalid search response.", response_status_code)
        items = [normalize_ticket(item) for item in payload["results"]]
        total = payload.get("total") if isinstance(payload.get("total"), int) else None
        next_page = request.page + 1 if request.page < 10 and len(items) >= 30 else None
        return SearchPage(
            items=items,
            total=total,
            pagination=PageInfo(
                page=request.page,
                per_page=len(items) if items else 30,
                has_more=next_page is not None,
                next_page=next_page,
            ),
        )

    async def _request(self, path: str, *, params: dict[str, str | int]) -> httpx.Response:
        last_retry_after: float | None = None
        for attempt in range(self.settings.max_retries + 1):
            await self._limiter.acquire()
            try:
                response = await self._http.get(
                    f"{self.settings.base_url}{path}",
                    params=params,
                    auth=(self.settings.api_key or "", "X"),
                    headers={"Accept": "application/json"},
                )
            except httpx.TimeoutException as exc:
                if attempt < self.settings.max_retries:
                    await self._sleep(self._backoff(attempt))
                    continue
                raise NetworkError("The Freshdesk request timed out.") from exc
            except httpx.RequestError as exc:
                if attempt < self.settings.max_retries:
                    await self._sleep(self._backoff(attempt))
                    continue
                raise NetworkError() from exc

            if response.status_code == 429:
                last_retry_after = self._retry_after(response)
                if attempt < self.settings.max_retries:
                    await self._sleep(
                        last_retry_after if last_retry_after is not None else self._backoff(attempt)
                    )
                    continue
                raise RateLimitError(last_retry_after)

            if response.status_code in {500, 502, 503, 504}:
                if attempt < self.settings.max_retries:
                    await self._sleep(self._backoff(attempt))
                    continue
                raise UpstreamError("Freshdesk returned a temporary server error.", response.status_code)

            if response.status_code >= 400:
                raise self._error_for_response(response)
            return response

        raise RateLimitError(last_retry_after)

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError("Freshdesk returned malformed JSON.", response.status_code) from exc

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("retry-after")
        if value is None:
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None

    def _backoff(self, attempt: int) -> float:
        return min(10.0, self.settings.retry_base_seconds * (2**attempt))

    @staticmethod
    def _next_page(link_header: str | None) -> int | None:
        if not link_header:
            return None
        match = _NEXT_LINK.search(link_header)
        if not match:
            return None
        page_values = parse_qs(urlparse(match.group(1)).query).get("page")
        if not page_values:
            return None
        try:
            page = int(page_values[0])
        except ValueError:
            return None
        return page if page >= 1 else None

    @staticmethod
    def _error_for_response(response: httpx.Response) -> ConnectorError:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        message = safe_upstream_message(payload)
        if response.status_code == 401:
            return AuthenticationError()
        if response.status_code == 403:
            return PermissionDeniedError()
        if response.status_code == 404:
            return NotFoundError()
        if response.status_code in {400, 405, 406, 415}:
            return BadRequestError(message)
        return UpstreamError(message, response.status_code)
