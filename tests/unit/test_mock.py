from __future__ import annotations

import pytest

from connector.errors import NotFoundError
from connector.models import GetTicketRequest, ListTicketsRequest, SearchTicketsRequest
from connector.service import build_service


@pytest.mark.asyncio
async def test_mock_list_is_bounded_and_supports_pagination() -> None:
    service = build_service()
    first = await service.list_tickets(ListTicketsRequest(per_page=2))
    second = await service.list_tickets(ListTicketsRequest(per_page=2, page=2))

    assert [ticket.id for ticket in first.items] == [10001, 10002]
    assert [ticket.id for ticket in second.items] == [10003, 10004]
    assert first.pagination.has_more is True
    assert first.pagination.next_page == 2
    assert all(ticket.requester.email.endswith("@fictional.test") for ticket in first.items if ticket.requester)


@pytest.mark.asyncio
async def test_mock_search_matches_tags_and_empty_results() -> None:
    service = build_service()
    matches = await service.search_tickets(SearchTicketsRequest(query="tag:'payment-failure'"))
    empty = await service.search_tickets(SearchTicketsRequest(query="tag:'does-not-exist'"))

    assert matches.total == 2
    assert {ticket.id for ticket in matches.items} == {10001, 10005}
    assert empty.items == []
    assert empty.total == 0


@pytest.mark.asyncio
async def test_mock_get_missing_ticket_is_safe() -> None:
    service = build_service()
    with pytest.raises(NotFoundError, match="not found"):
        await service.get_ticket(GetTicketRequest(ticket_id=99999))
