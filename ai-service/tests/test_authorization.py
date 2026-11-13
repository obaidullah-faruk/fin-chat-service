import asyncio
from unittest.mock import AsyncMock

import pytest

from security.authorization import (
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_PERMISSIONS,
    ROLE_SUPERADMIN,
    ToolAuthorizationError,
    check_tool_authorization,
    filter_tools_for_role,
    get_role_permissions,
    is_tool_allowed,
)


def test_customer_allowed_and_denied_tools():
    # Customer allowed tools
    assert is_tool_allowed(ROLE_CUSTOMER, "get_balance") is True
    assert is_tool_allowed(ROLE_CUSTOMER, "get_account_info") is True
    assert is_tool_allowed(ROLE_CUSTOMER, "get_transactions") is True
    assert is_tool_allowed(ROLE_CUSTOMER, "get_statement") is True
    assert is_tool_allowed(ROLE_CUSTOMER, "request_cheque_book") is True

    # Customer denied tools
    assert is_tool_allowed(ROLE_CUSTOMER, "update_address") is False
    assert is_tool_allowed(ROLE_CUSTOMER, "get_kyc_status") is False
    assert is_tool_allowed(ROLE_CUSTOMER, "arbitrary_tool") is False


def test_manager_allowed_tools():
    # Manager has all customer tools + service manager tools
    for tool in [
        "get_balance",
        "get_account_info",
        "get_transactions",
        "get_statement",
        "request_cheque_book",
        "update_address",
        "get_kyc_status",
    ]:
        assert is_tool_allowed(ROLE_MANAGER, tool) is True

    assert is_tool_allowed(ROLE_MANAGER, "delete_database") is False


def test_admin_and_superadmin_all_tools():
    assert is_tool_allowed(ROLE_ADMIN, "get_balance") is True
    assert is_tool_allowed(ROLE_ADMIN, "update_address") is True
    assert is_tool_allowed(ROLE_ADMIN, "any_custom_tool") is True

    assert is_tool_allowed(ROLE_SUPERADMIN, "get_balance") is True
    assert is_tool_allowed(ROLE_SUPERADMIN, "update_address") is True
    assert is_tool_allowed(ROLE_SUPERADMIN, "any_custom_tool") is True


def test_invalid_or_empty_roles():
    assert is_tool_allowed(None, "get_balance") is False
    assert is_tool_allowed("", "get_balance") is False
    assert is_tool_allowed("unknown_role", "get_balance") is False
    assert is_tool_allowed("customer", "") is False


def test_check_tool_authorization_raises_on_denial():
    # Authorized does not raise
    check_tool_authorization(ROLE_CUSTOMER, "get_balance")
    check_tool_authorization(ROLE_MANAGER, "update_address")

    # Unauthorized raises ToolAuthorizationError
    with pytest.raises(ToolAuthorizationError) as exc_info:
        check_tool_authorization(ROLE_CUSTOMER, "update_address")

    assert "role 'customer' is not authorized to execute tool 'update_address'" in str(
        exc_info.value
    )
    assert exc_info.value.role == "customer"
    assert exc_info.value.tool_name == "update_address"


def test_filter_tools_for_role():
    all_tools = [
        "get_balance",
        "get_account_info",
        "update_address",
        "get_kyc_status",
        "unknown_action",
    ]

    customer_tools = filter_tools_for_role(all_tools, ROLE_CUSTOMER)
    assert customer_tools == ["get_balance", "get_account_info"]

    manager_tools = filter_tools_for_role(all_tools, ROLE_MANAGER)
    assert manager_tools == [
        "get_balance",
        "get_account_info",
        "update_address",
        "get_kyc_status",
    ]

    admin_tools = filter_tools_for_role(all_tools, ROLE_ADMIN)
    assert admin_tools == all_tools


def test_get_role_permissions():
    assert isinstance(get_role_permissions(ROLE_CUSTOMER), set)
    assert "get_balance" in get_role_permissions(ROLE_CUSTOMER)
    assert get_role_permissions(ROLE_ADMIN) == "__all__"
    assert get_role_permissions("non_existent") == set()
    assert get_role_permissions(None) == set()


def test_role_case_insensitivity():
    assert is_tool_allowed("CUSTOMER", "get_balance") is True
    assert is_tool_allowed(" Customer ", "get_balance") is True
    assert is_tool_allowed("MANAGER", "update_address") is True


def test_mcp_tool_binding_authorization_enforcement():
    from mcp_client import (
        DiscoveredMCPTool,
        StructuredTool,
        ToolCallTelemetry,
        bind_mcp_tools_for_user,
    )

    backend_called = []

    async def fake_update_address(**kwargs):
        backend_called.append(kwargs)
        return '{"status": "updated"}'

    async def fake_get_balance(**kwargs):
        backend_called.append(kwargs)
        return '{"balance": "1000.00"}'

    balance_tool = StructuredTool.from_function(
        coroutine=fake_get_balance,
        name="get_balance",
        description="Get balance",
    )
    address_tool = StructuredTool.from_function(
        coroutine=fake_update_address,
        name="update_address",
        description="Update address",
    )

    discovered = [
        DiscoveredMCPTool(server_name="accounts", tool=balance_tool),
        DiscoveredMCPTool(server_name="service", tool=address_tool),
    ]

    # Test customer role: can call balance, blocked on address
    customer_telemetry: list[ToolCallTelemetry] = []
    customer_tools = bind_mcp_tools_for_user(
        discovered,
        user_id=10,
        role="customer",
        telemetry_records=customer_telemetry,
    )
    tools_by_name = {t.name: t for t in customer_tools}

    # Calling get_balance as customer succeeds
    balance_res = asyncio.run(tools_by_name["get_balance"].ainvoke({}))
    assert "1000.00" in balance_res
    assert len(backend_called) == 1

    # Calling update_address as customer fails before reaching backend
    with pytest.raises(ToolAuthorizationError) as exc_info:
        asyncio.run(tools_by_name["update_address"].ainvoke({"new_address": "Dhaka"}))

    assert "role 'customer' is not authorized to execute tool 'update_address'" in str(
        exc_info.value
    )
    assert len(backend_called) == 1  # backend was NOT called!
    assert len(customer_telemetry) == 2
    assert customer_telemetry[-1].success is False
    assert "Permission denied" in (customer_telemetry[-1].error_message or "")

    # Test manager role: can call update_address
    manager_telemetry: list[ToolCallTelemetry] = []
    manager_tools = bind_mcp_tools_for_user(
        discovered,
        user_id=20,
        role="manager",
        telemetry_records=manager_telemetry,
    )
    mgr_tools_by_name = {t.name: t for t in manager_tools}
    addr_res = asyncio.run(mgr_tools_by_name["update_address"].ainvoke({"new_address": "Dhaka"}))
    assert "updated" in addr_res
    assert len(backend_called) == 2
    assert manager_telemetry[-1].success is True

