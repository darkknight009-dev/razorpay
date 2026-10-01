"""Use-case layer shared by MCP tools, mock mode, and live mode."""

from __future__ import annotations

import httpx

from .client import FreshdeskClient
from .config import Settings
from .errors import ValidationError
from .mock import MockTicketSource
from .models import (
    GetTicketRequest,
    ListTicketsRequest,
    SearchPage,
    SearchTicketsRequest,
    Ticket,
    TicketPage,
)
from .source import TicketSource, close_source


class ConnectorService:
    def __init__(self, source: TicketSource, settings: Settings) -> None:
        self.source = source
        self.settings = settings

    async def list_tickets(self, request: ListTicketsRequest) -> TicketPage:
        if request.page > self.settings.max_list_pages:
            raise ValidationError(
                f"page must be no greater than the connector limit of {self.settings.max_list_pages}."
            )
        if request.page * request.per_page > self.settings.max_list_results:
            raise ValidationError(
                f"requested page exceeds the connector result limit of "
                f"{self.settings.max_list_results}."
            )
        return await self.source.list_tickets(request)

    async def get_ticket(self, request: GetTicketRequest) -> Ticket:
        return await self.source.get_ticket(request)

    async def search_tickets(self, request: SearchTicketsRequest) -> SearchPage:
        if request.page > min(10, self.settings.max_list_pages):
            raise ValidationError(
                f"search page must be no greater than {min(10, self.settings.max_list_pages)}."
            )
        return await self.source.search_tickets(request)

    async def aclose(self) -> None:
        await close_source(self.source)


def build_service(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> ConnectorService:
    settings = settings or Settings.from_env()
    if settings.mock_mode:
        source: TicketSource = MockTicketSource()
    else:
        source = FreshdeskClient(settings, http_client=http_client)
    return ConnectorService(source, settings)
