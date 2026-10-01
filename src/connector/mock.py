"""Deterministic fictional ticket source for demos and offline tests."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .errors import NotFoundError
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

MOCK_TICKETS: list[dict[str, Any]] = [
    {
        "id": 10001,
        "subject": "Payment failed after retry",
        "description_text": "Fictional checkout payment failure in the demo environment.",
        "status": 2,
        "priority": 4,
        "type": "Problem",
        "requester_id": 91001,
        "requester": {"id": 91001, "name": "Riya Demo", "email": "riya@fictional.test"},
        "tags": ["payment-failure", "checkout"],
        "created_at": "2026-09-30T10:00:00Z",
        "updated_at": "2026-09-30T10:15:00Z",
        "custom_fields": {"demo_record": True},
    },
    {
        "id": 10002,
        "subject": "Change delivery address",
        "description_text": "Fictional customer asks how to update a delivery address.",
        "status": 2,
        "priority": 2,
        "type": "Question",
        "requester_id": 91002,
        "requester": {"id": 91002, "name": "Aarav Demo", "email": "aarav@fictional.test"},
        "tags": ["delivery"],
        "created_at": "2026-09-29T09:00:00Z",
        "updated_at": "2026-09-29T09:30:00Z",
        "custom_fields": {"demo_record": True},
    },
    {
        "id": 10003,
        "subject": "Payment pending in sandbox",
        "description_text": "Fictional sandbox payment remains pending.",
        "status": 3,
        "priority": 3,
        "type": "Problem",
        "requester_id": 91003,
        "requester": {"id": 91003, "name": "Kabir Demo", "email": "kabir@fictional.test"},
        "tags": ["payment", "sandbox"],
        "created_at": "2026-09-28T12:00:00Z",
        "updated_at": "2026-09-29T08:30:00Z",
        "custom_fields": {"demo_record": True},
    },
    {
        "id": 10004,
        "subject": "Webhook delivery delay",
        "description_text": "Fictional webhook delivery is delayed in the demo account.",
        "status": 4,
        "priority": 3,
        "type": "Problem",
        "requester_id": 91004,
        "requester": {"id": 91004, "name": "Meera Demo", "email": "meera@fictional.test"},
        "tags": ["webhook"],
        "created_at": "2026-09-27T14:00:00Z",
        "updated_at": "2026-09-28T09:00:00Z",
        "custom_fields": {"demo_record": True},
    },
    {
        "id": 10005,
        "subject": "Payment failed for a fictional order",
        "description_text": "Fictional order payment failed before confirmation.",
        "status": 2,
        "priority": 3,
        "type": "Problem",
        "requester_id": 91005,
        "requester": {"id": 91005, "name": "Dev Demo", "email": "dev@fictional.test"},
        "tags": ["payment-failure", "orders"],
        "created_at": "2026-09-26T16:00:00Z",
        "updated_at": "2026-09-27T11:00:00Z",
        "custom_fields": {"demo_record": True},
    },
]

_CONDITION = re.compile(r"^([a-z_]+):(?:'([^']*)'|\"([^\"]*)\"|([^\s()]+))$", re.IGNORECASE)


class MockTicketSource:
    """In-memory source whose records are intentionally synthetic."""

    async def list_tickets(self, request: ListTicketsRequest) -> TicketPage:
        records = [deepcopy(ticket) for ticket in MOCK_TICKETS]
        if request.email:
            records = [
                ticket
                for ticket in records
                if ticket.get("requester", {}).get("email") == request.email
            ]
        if request.requester_id is not None:
            records = [ticket for ticket in records if ticket.get("requester_id") == request.requester_id]
        if request.filter == "new_and_my_open":
            records = [ticket for ticket in records if ticket.get("status") == 2]
        if request.filter == "spam":
            records = []
        if request.filter == "deleted":
            records = []

        sort_key = request.order_by
        records.sort(key=lambda ticket: ticket.get(sort_key) or 0, reverse=request.order_type == "desc")
        start = (request.page - 1) * request.per_page
        page_records = records[start : start + request.per_page]
        has_more = start + request.per_page < len(records)
        return TicketPage(
            items=[normalize_ticket(ticket) for ticket in page_records],
            pagination=PageInfo(
                page=request.page,
                per_page=request.per_page,
                has_more=has_more,
                next_page=request.page + 1 if has_more else None,
            ),
        )

    async def get_ticket(self, request: GetTicketRequest) -> Ticket:
        for ticket in MOCK_TICKETS:
            if ticket["id"] == request.ticket_id:
                return normalize_ticket(deepcopy(ticket))
        raise NotFoundError("ticket")

    async def search_tickets(self, request: SearchTicketsRequest) -> SearchPage:
        records = [deepcopy(ticket) for ticket in MOCK_TICKETS if _matches(request.query, ticket)]
        page_size = 30
        start = (request.page - 1) * page_size
        page_records = records[start : start + page_size]
        has_more = start + page_size < len(records) and request.page < 10
        return SearchPage(
            items=[normalize_ticket(ticket) for ticket in page_records],
            total=len(records),
            pagination=PageInfo(
                page=request.page,
                per_page=page_size,
                has_more=has_more,
                next_page=request.page + 1 if has_more else None,
            ),
        )


def _matches(query: str, ticket: dict[str, Any]) -> bool:
    """Evaluate the small documented subset needed by deterministic demo fixtures."""

    query = query.strip()
    if not query:
        return False
    return _evaluate(query, ticket)


def _evaluate(expression: str, ticket: dict[str, Any]) -> bool:
    expression = _strip_outer_parentheses(expression.strip())
    parts = _split_top_level(expression, "OR")
    if len(parts) > 1:
        return any(_evaluate(part, ticket) for part in parts)
    parts = _split_top_level(expression, "AND")
    if len(parts) > 1:
        return all(_evaluate(part, ticket) for part in parts)
    match = _CONDITION.fullmatch(expression)
    if not match:
        return False
    field, single, double, bare = match.groups()
    value = (single if single is not None else double if double is not None else bare or "").lower()
    field = field.lower()
    if field == "tag":
        return value == "null" and not ticket.get("tags") or value in [str(tag).lower() for tag in ticket.get("tags", [])]
    if field in {"priority", "status"}:
        try:
            return ticket.get(field) == int(value)
        except ValueError:
            return False
    if field == "type":
        return value == "null" and ticket.get("type") is None or str(ticket.get("type", "")).lower() == value
    if field in {"email", "requester_email"}:
        return ticket.get("requester", {}).get("email", "").lower() == value
    if field == "custom_string":
        haystack = " ".join(
            [
                str(ticket.get("subject", "")),
                str(ticket.get("description_text", "")),
                " ".join(ticket.get("tags", [])),
            ]
        ).lower()
        return value in haystack
    return False


def _split_top_level(expression: str, operator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    token = f" {operator} "
    index = 0
    while index < len(expression):
        char = expression[index]
        if quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and expression[index : index + len(token)].upper() == token:
            parts.append(expression[start:index])
            index += len(token)
            start = index
            continue
        index += 1
    if parts:
        parts.append(expression[start:])
    return parts or [expression]


def _strip_outer_parentheses(expression: str) -> str:
    while expression.startswith("(") and expression.endswith(")"):
        depth = 0
        quote: str | None = None
        closes_at: int | None = None
        for index, char in enumerate(expression):
            if quote:
                if char == quote:
                    quote = None
            elif char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    closes_at = index
                    break
        if closes_at == len(expression) - 1:
            expression = expression[1:-1].strip()
        else:
            break
    return expression
