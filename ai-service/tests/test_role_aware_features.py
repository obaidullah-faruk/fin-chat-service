import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.tools import StructuredTool

from security.authorization import (
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_ADMIN,
    ROLE_SUPERADMIN,
    is_tool_allowed,
    check_tool_authorization,
    ToolAuthorizationError,
)
from mcp_client import (
    DiscoveredMCPTool,
    bind_mcp_tools_for_user,
    partition_mcp_tools_by_domain,
)


def test_customer_role_permissions():
    # Customer allowed tools
    assert is_tool_allowed(ROLE_CUSTOMER, "get_balance") is True
    assert is_tool_allowed(ROLE_CUSTOMER, "get_transactions") is True
    assert is_tool_allowed(ROLE_CUSTOMER, "get_transaction_by_reference") is True
    assert is_tool_allowed(ROLE_CUSTOMER, "lookup_account") is True

    # Customer denied tools
    assert is_tool_allowed(ROLE_CUSTOMER, "get_bank_dashboard_summary") is False
    assert is_tool_allowed(ROLE_CUSTOMER, "lookup_customer") is False
    assert is_tool_allowed(ROLE_CUSTOMER, "get_pending_reviews") is False

    with pytest.raises(ToolAuthorizationError):
        check_tool_authorization(ROLE_CUSTOMER, "get_bank_dashboard_summary")

    with pytest.raises(ToolAuthorizationError):
        check_tool_authorization(ROLE_CUSTOMER, "lookup_customer")

    with pytest.raises(ToolAuthorizationError):
        check_tool_authorization(ROLE_CUSTOMER, "get_pending_reviews")


def test_manager_role_permissions():
    # Manager has access to operational inspection tools
    assert is_tool_allowed(ROLE_MANAGER, "get_transaction_by_reference") is True
    assert is_tool_allowed(ROLE_MANAGER, "lookup_account") is True
    assert is_tool_allowed(ROLE_MANAGER, "lookup_customer") is True
    assert is_tool_allowed(ROLE_MANAGER, "get_bank_dashboard_summary") is True
    assert is_tool_allowed(ROLE_MANAGER, "get_pending_reviews") is True
    assert is_tool_allowed(ROLE_MANAGER, "get_kyc_status") is True


def test_admin_superadmin_role_permissions():
    for role in [ROLE_ADMIN, ROLE_SUPERADMIN]:
        assert is_tool_allowed(role, "get_transaction_by_reference") is True
        assert is_tool_allowed(role, "lookup_account") is True
        assert is_tool_allowed(role, "lookup_customer") is True
        assert is_tool_allowed(role, "get_bank_dashboard_summary") is True
        assert is_tool_allowed(role, "get_pending_reviews") is True


def test_partition_mcp_tools_includes_new_tools():
    tools = [
        DiscoveredMCPTool(server_name="accounts", tool=MagicMock(name="get_balance")),
        DiscoveredMCPTool(server_name="accounts", tool=MagicMock(name="lookup_account")),
        DiscoveredMCPTool(server_name="accounts", tool=MagicMock(name="get_bank_dashboard_summary")),
        DiscoveredMCPTool(server_name="transactions", tool=MagicMock(name="get_transaction_by_reference")),
        DiscoveredMCPTool(server_name="service", tool=MagicMock(name="lookup_customer")),
        DiscoveredMCPTool(server_name="service", tool=MagicMock(name="get_pending_reviews")),
    ]
    partitioned = partition_mcp_tools_by_domain(tools)
    assert len(partitioned["accounts"]) == 3
    assert len(partitioned["transactions"]) == 1
    assert len(partitioned["service"]) == 2


def test_tool_binding_pii_de_anonymization():
    mock_base_tool = MagicMock()
    mock_base_tool.name = "lookup_account"
    mock_base_tool.description = "Look up account"
    mock_base_tool.args_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "user_id": {"type": "integer"}},
        "required": ["query"],
    }
    
    invoked_args = {}

    async def mock_coro(*args, **kwargs):
        if args and isinstance(args[0], dict):
            invoked_args.update(args[0])
        invoked_args.update(kwargs)
        return '{"status": "ok"}'

    mock_base_tool.ainvoke = AsyncMock(side_effect=mock_coro)

    discovered = [DiscoveredMCPTool(server_name="accounts", tool=mock_base_tool)]
    pii_mapping = {"<ACCOUNT_NUMBER>": "FC1000000001"}

    bound = bind_mcp_tools_for_user(
        discovered,
        user_id=1,
        role="superadmin",
        pii_mapping=pii_mapping,
    )

    assert len(bound) == 1
    tool = bound[0]
    asyncio.run(tool.ainvoke({"query": "<ACCOUNT_NUMBER>"}))

    # Assert that <ACCOUNT_NUMBER> was de-anonymized to FC1000000001
    assert invoked_args["query"] == "FC1000000001"
    assert invoked_args["user_id"] == 1
