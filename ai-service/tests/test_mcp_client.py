import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_client import StructuredTool

try:
    from langchain_core.tools import ToolException
except ImportError:
    class ToolException(Exception):  # type: ignore[no-redef]
        pass
import pytest

import mcp_client
from mcp_client import (
    DiscoveredMCPTool,
    ToolCallTelemetry,
    bind_mcp_tools_for_user,
    clear_mcp_tool_cache,
    discover_mcp_tools,
    get_discovered_mcp_tools,
)


def _make_fake_mcp_tool(name: str, args_schema: dict, handler):
    return StructuredTool.from_function(
        coroutine=handler,
        name=name,
        description=f"Fake {name}",
        args_schema=args_schema,
    )


def test_discover_mcp_tools_preserves_server_ownership(monkeypatch):
    monkeypatch.setenv("ACCOUNTS_MCP_URL", "http://accounts-mcp:8002/mcp")
    monkeypatch.setenv("TRANSACTIONS_MCP_URL", "http://transactions-mcp:8003/mcp")
    monkeypatch.setenv("SERVICE_MCP_URL", "http://service-mcp:8004/mcp")

    async def noop(**kwargs):
        return "{}"

    acc_tool = _make_fake_mcp_tool(
        "get_balance",
        {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
        noop,
    )
    txn_tool = _make_fake_mcp_tool(
        "get_transactions",
        {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
        noop,
    )
    svc_tool = _make_fake_mcp_tool(
        "get_kyc_status",
        {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
        noop,
    )

    mock_client = MagicMock()

    async def fake_get_tools(*, server_name: str):
        return {
            "accounts": [acc_tool],
            "transactions": [txn_tool],
            "service": [svc_tool],
        }[server_name]

    mock_client.get_tools = AsyncMock(side_effect=fake_get_tools)

    discovered = asyncio.run(discover_mcp_tools(client=mock_client))
    assert [(item.server_name, item.tool.name) for item in discovered] == [
        ("accounts", "get_balance"),
        ("transactions", "get_transactions"),
        ("service", "get_kyc_status"),
    ]


def test_bind_mcp_tools_strips_user_id_injects_verified_id_and_records_telemetry():
    captured_calls: list[dict] = []

    async def fake_get_transactions(**kwargs):
        captured_calls.append(kwargs)
        return [
            {
                "type": "text",
                "text": '{"account_number": "FC1000000001", "transactions": [{"amount": "100.00"}]}',
            }
        ]

    base_tool = _make_fake_mcp_tool(
        "get_transactions",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["user_id"],
        },
        fake_get_transactions,
    )
    telemetry: list[ToolCallTelemetry] = []
    bound = bind_mcp_tools_for_user(
        [DiscoveredMCPTool(server_name="transactions", tool=base_tool)],
        user_id=42,
        telemetry_records=telemetry,
    )

    assert len(bound) == 1
    tool = bound[0]
    assert "user_id" not in tool.args_schema["properties"]
    assert "user_id" not in tool.args_schema["required"]
    assert "limit" in tool.args_schema["properties"]

    # Even if a spoofed user_id were somehow passed in kwargs, verified user_id=42 wins.
    output = asyncio.run(tool.ainvoke({"limit": 5, "user_id": 999}))
    assert '"account_number": "FC1000000001"' in output
    assert captured_calls == [{"limit": 5, "user_id": 42}]

    assert len(telemetry) == 1
    record = telemetry[0]
    assert record.tool_name == "get_transactions"
    assert record.mcp_server == "transactions"
    assert record.input_json == {"limit": 5, "user_id": 42}
    assert record.output_json["account_number"] == "FC1000000001"
    assert record.success is True
    assert record.error_message is None
    assert record.latency_ms >= 0


def test_bind_mcp_tools_records_failure_telemetry_and_reraises():
    async def failing_tool(**kwargs):
        raise ToolException("404 Not Found from Django")

    base_tool = _make_fake_mcp_tool(
        "get_balance",
        {"type": "object", "properties": {"user_id": {"type": "integer"}}, "required": ["user_id"]},
        failing_tool,
    )
    telemetry: list[ToolCallTelemetry] = []
    bound = bind_mcp_tools_for_user(
        [DiscoveredMCPTool(server_name="accounts", tool=base_tool)],
        user_id=7,
        telemetry_records=telemetry,
    )

    with pytest.raises(ToolException, match="404 Not Found"):
        asyncio.run(bound[0].ainvoke({}))

    assert len(telemetry) == 1
    record = telemetry[0]
    assert record.tool_name == "get_balance"
    assert record.mcp_server == "accounts"
    assert record.input_json == {"user_id": 7}
    assert record.output_json == {}
    assert record.success is False
    assert "404 Not Found" in (record.error_message or "")


def test_get_discovered_mcp_tools_caches_results():
    clear_mcp_tool_cache()
    fake_entry = DiscoveredMCPTool(server_name="accounts", tool=MagicMock(name="get_balance"))

    with patch.object(
        mcp_client,
        "discover_mcp_tools",
        new=AsyncMock(return_value=[fake_entry]),
    ) as mock_discover:
        first = asyncio.run(get_discovered_mcp_tools())
        second = asyncio.run(get_discovered_mcp_tools())
        refreshed = asyncio.run(get_discovered_mcp_tools(force_refresh=True))

    assert first == [fake_entry]
    assert second == [fake_entry]
    assert refreshed == [fake_entry]
    assert mock_discover.await_count == 2
    clear_mcp_tool_cache()

