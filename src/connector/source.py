"""Shared ticket-source protocol for live and mock implementations."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol

from .models import (
    GetTicketRequest,
    ListTicketsRequest,
    SearchPage,
    SearchTicketsRequest,
    Ticket,
    TicketPage,
)


class TicketSource(Protocol):
    def list_tickets(self, request: ListTicketsRequest) -> Awaitable[TicketPage]: ...

    def get_ticket(self, request: GetTicketRequest) -> Awaitable[Ticket]: ...

    def search_tickets(self, request: SearchTicketsRequest) -> Awaitable[SearchPage]: ...


async def close_source(source: object) -> None:
    close = getattr(source, "aclose", None)
    if close is not None:
        await close()
