from __future__ import annotations

import pytest

from connector.config import Settings
from connector.mcp_server import create_server
from connector.service import build_service


@pytest.mark.asyncio
async def test_mcp_exposes_three_read_only_tools_and_structured_result() -> None:
    server = create_server(build_service(Settings(mock_mode=True)))
    tools = await server.list_tools()

    assert [tool.name for tool in tools] == ["list_tickets", "get_ticket", "search_tickets"]
    assert all(tool.annotations.read_only_hint is True for tool in tools)
    assert all(tool.input_schema["type"] == "object" for tool in tools)

    result = await server.call_tool("search_tickets", {"query": "tag:'payment-failure'"})
    assert result.is_error is False
    assert result.structured_content["total"] == 2
    assert {item["id"] for item in result.structured_content["items"]} == {10001, 10005}


@pytest.mark.asyncio
async def test_mcp_rejects_invalid_tool_input() -> None:
    server = create_server(build_service(Settings(mock_mode=True)))

    with pytest.raises(Exception, match="ticket_id"):
        await server.call_tool("get_ticket", {"ticket_id": 0})
