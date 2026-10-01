"""One-command offline demonstration of the connector service."""

from __future__ import annotations

import asyncio
import json

from connector.errors import ConnectorError
from connector.models import GetTicketRequest, ListTicketsRequest, SearchTicketsRequest
from connector.service import build_service


async def run_demo() -> None:
    service = build_service()
    try:
        search = await service.search_tickets(SearchTicketsRequest(query="tag:'payment-failure'"))
        print("Search: tickets related to fictional payment failures")
        print(json.dumps(search.model_dump(mode="json"), indent=2))

        first = await service.list_tickets(ListTicketsRequest(per_page=2, order_by="created_at"))
        second = await service.list_tickets(
            ListTicketsRequest(per_page=2, page=2, order_by="created_at")
        )
        print("\nPagination: first page IDs", [ticket.id for ticket in first.items])
        print("Pagination: second page IDs", [ticket.id for ticket in second.items])

        ticket = await service.get_ticket(GetTicketRequest(ticket_id=10001))
        print("\nGet ticket 10001:")
        print(json.dumps(ticket.model_dump(mode="json"), indent=2))

        try:
            await service.get_ticket(GetTicketRequest(ticket_id=99999))
        except ConnectorError as error:
            print("\nSafe missing-ticket error:", error.public_message())
    finally:
        await service.aclose()


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
