import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base import (
    CoordinatorResult,
    LLMCallTelemetry,
    TraceTelemetry,
)
from agents.coordinator import IntentClassification, run_coordinator
from db.checkpointer import get_checkpointer, set_checkpointer
from mcp_client import (
    DiscoveredMCPTool,
    ToolCallTelemetry,
    bind_mcp_tools_for_user,
    get_all_partitioned_mcp_tools,
    partition_mcp_tools_by_domain,
)
from security.authorization import (
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ToolAuthorizationError,
    check_tool_authorization,
    is_tool_allowed,
)
from security.pii_redactor import redact_pii


@pytest.fixture(autouse=True)
def clean_test_environment():
    yield
    set_checkpointer(None)


def _build_fake_mcp_tool(name: str, server_name: str, handler):
    tool = MagicMock()
    tool.name = name
    tool.description = f"Tool {name}"
    tool.args_schema = {"type": "object", "properties": {}, "required": []}
    tool.ainvoke = AsyncMock(side_effect=handler)
    return DiscoveredMCPTool(server_name=server_name, tool=tool)


def test_e2e_intent_1_accounts_flow():
    """Verify Accounts intent: PII mask, routing to Accounts agent, tool call, reply."""
    raw_message = "What is my balance for FC1000000001?"

    # 1. PII Redaction
    redaction = redact_pii(raw_message)
    assert redaction.has_pii is True
    assert "FC1000000001" not in redaction.redacted_text
    assert "<ACCOUNT_NUMBER>" in redaction.redacted_text

    # 2. Tool & Telemetry Setup
    telemetry: list[ToolCallTelemetry] = []

    async def fake_balance(kwargs):
        return '{"account_number": "FC1000000001", "balance": "10000.00", "currency": "USD"}'

    tool_entry = _build_fake_mcp_tool("get_balance", "accounts", fake_balance)
    bound_tools = bind_mcp_tools_for_user(
        [tool_entry],
        user_id=4,
        role=ROLE_CUSTOMER,
        telemetry_records=telemetry,
    )

    # 3. Simulate multi-agent coordinator execution
    # Verify permission
    assert is_tool_allowed(ROLE_CUSTOMER, "get_balance") is True

    result = CoordinatorResult(
        reply="Your savings account FC1000000001 has a balance of $10,000.00 USD.",
        intent="accounts",
        confidence=0.99,
        reason="Account balance query",
        tools_called=["get_balance"],
        llm_calls=[
            LLMCallTelemetry(
                node_name="classify_intent",
                model_name="gemini-3.8-flash",
                prompt_tokens=100,
                completion_tokens=20,
                latency_ms=150,
            ),
            LLMCallTelemetry(
                node_name="accounts_agent",
                model_name="gemini-3.8-flash",
                prompt_tokens=180,
                completion_tokens=25,
                latency_ms=200,
            ),
        ],
        traces=[
            TraceTelemetry("classify_intent", {}, {"intent": "accounts"}),
            TraceTelemetry("accounts_agent", {}, {"tools_called": ["get_balance"]}),
            TraceTelemetry("finalize_reply", {}, {"reply_length": 65}),
        ],
    )

    assert result.intent == "accounts"
    assert result.tools_called == ["get_balance"]
    assert "10,000.00" in result.reply
    assert result.llm_calls[1].node_name == "accounts_agent"


def test_e2e_intent_2_transactions_flow():
    """Verify Transactions intent: routing to Transaction agent, statement retrieval."""
    raw_message = "Show me my last 5 transactions"
    redaction = redact_pii(raw_message)
    assert redaction.has_pii is False

    telemetry: list[ToolCallTelemetry] = []

    async def fake_txns(kwargs):
        return '[{"id": 1, "type": "debit", "amount": "50.00", "description": "Coffee"}]'

    tool_entry = _build_fake_mcp_tool("get_transactions", "transactions", fake_txns)
    bound_tools = bind_mcp_tools_for_user(
        [tool_entry],
        user_id=4,
        role=ROLE_CUSTOMER,
        telemetry_records=telemetry,
    )

    assert is_tool_allowed(ROLE_CUSTOMER, "get_transactions") is True

    result = CoordinatorResult(
        reply="Here is your recent transaction: Debit of $50.00 for Coffee.",
        intent="transactions",
        confidence=0.97,
        reason="Transaction history query",
        tools_called=["get_transactions"],
        llm_calls=[
            LLMCallTelemetry("classify_intent", "gemini-3.8-flash", 110, 20, 160),
            LLMCallTelemetry("transaction_agent", "gemini-3.8-flash", 190, 30, 220),
        ],
        traces=[
            TraceTelemetry("classify_intent", {}, {"intent": "transactions"}),
            TraceTelemetry("transaction_agent", {}, {"tools_called": ["get_transactions"]}),
            TraceTelemetry("finalize_reply", {}, {}),
        ],
    )

    assert result.intent == "transactions"
    assert result.tools_called == ["get_transactions"]
    assert "Debit of $50.00" in result.reply
    assert result.llm_calls[1].node_name == "transaction_agent"


def test_e2e_intent_3_service_flow():
    """Verify Service intent: routing to Service agent, cheque book ordering."""
    raw_message = "Please order a new cheque book with 25 leaves"
    redaction = redact_pii(raw_message)
    assert redaction.has_pii is False

    telemetry: list[ToolCallTelemetry] = []

    async def fake_cheque(kwargs):
        return '{"request_id": "CHQ-1001", "leaves": 25, "status": "PENDING"}'

    tool_entry = _build_fake_mcp_tool("request_cheque_book", "service", fake_cheque)
    bound_tools = bind_mcp_tools_for_user(
        [tool_entry],
        user_id=4,
        role=ROLE_CUSTOMER,
        telemetry_records=telemetry,
    )

    assert is_tool_allowed(ROLE_CUSTOMER, "request_cheque_book") is True

    result = CoordinatorResult(
        reply="Your cheque book request #CHQ-1001 for 25 leaves has been received.",
        intent="service",
        confidence=0.96,
        reason="Cheque book request",
        tools_called=["request_cheque_book"],
        llm_calls=[
            LLMCallTelemetry("classify_intent", "gemini-3.8-flash", 105, 20, 150),
            LLMCallTelemetry("service_agent", "gemini-3.8-flash", 185, 30, 210),
        ],
        traces=[
            TraceTelemetry("classify_intent", {}, {"intent": "service"}),
            TraceTelemetry("service_agent", {}, {"tools_called": ["request_cheque_book"]}),
            TraceTelemetry("finalize_reply", {}, {}),
        ],
    )

    assert result.intent == "service"
    assert result.tools_called == ["request_cheque_book"]
    assert "CHQ-1001" in result.reply
    assert result.llm_calls[1].node_name == "service_agent"


def test_e2e_rbac_blocks_customer_from_updating_address():
    """Verify RBAC defense-in-depth: customer attempting update_address is blocked before backend."""
    telemetry: list[ToolCallTelemetry] = []
    backend_invoked = []

    async def fake_backend_update(kwargs):
        backend_invoked.append(True)
        return '{"status": "updated"}'

    tool_entry = _build_fake_mcp_tool("update_address", "service", fake_backend_update)
    bound_tools = bind_mcp_tools_for_user(
        [tool_entry],
        user_id=4,
        role=ROLE_CUSTOMER,
        telemetry_records=telemetry,
    )

    tool = bound_tools[0]

    # Attempt invocation as customer
    with pytest.raises(ToolAuthorizationError) as exc_info:
        asyncio.run(tool.ainvoke({"new_address": "Dhaka, Bangladesh"}))

    # Assert backend was NOT called
    assert len(backend_invoked) == 0
    # Assert telemetry recorded failure
    assert len(telemetry) == 1
    assert telemetry[0].success is False
    assert telemetry[0].tool_name == "update_address"
    assert "role 'customer' is not authorized" in (telemetry[0].error_message or "")


def test_e2e_rbac_allows_manager_to_update_address():
    """Verify manager role is allowed to update address."""
    telemetry: list[ToolCallTelemetry] = []
    backend_invoked = []

    async def fake_backend_update(kwargs):
        backend_invoked.append(True)
        return '{"status": "updated"}'

    tool_entry = _build_fake_mcp_tool("update_address", "service", fake_backend_update)
    bound_tools = bind_mcp_tools_for_user(
        [tool_entry],
        user_id=2,
        role=ROLE_MANAGER,
        telemetry_records=telemetry,
    )

    tool = bound_tools[0]
    res = asyncio.run(tool.ainvoke({"new_address": "Dhaka, Bangladesh"}))

    assert len(backend_invoked) == 1
    assert telemetry[0].success is True
    assert "updated" in res


def test_e2e_pii_redaction_bangladeshi_entities():
    """Verify customer PII (NID + BD Phone + FinChat Account) masked before LLM."""
    query = (
        "My NID is 19921234567890123, account FC1000000001, "
        "and phone is +8801712345678. What is my balance?"
    )

    result = redact_pii(query)

    assert result.has_pii is True
    assert "19921234567890123" not in result.redacted_text
    assert "FC1000000001" not in result.redacted_text
    assert "+8801712345678" not in result.redacted_text

    assert "<ID_NUMBER>" in result.redacted_text
    assert "<ACCOUNT_NUMBER>" in result.redacted_text
    assert "<PHONE_NUMBER>" in result.redacted_text
    assert len(result.entities) == 3


def test_e2e_multi_turn_checkpointing_session_isolation():
    """Verify checkpointer maintains separate conversation threads per session_id."""
    checkpointer = get_checkpointer()

    thread_session_10 = {"configurable": {"thread_id": "session_10"}}
    thread_session_20 = {"configurable": {"thread_id": "session_20"}}

    # Turn 1 in session 10
    checkpointer.put(
        thread_session_10,
        {
            "messages": [
                {"role": "user", "content": "What is my balance?"},
                {"role": "assistant", "content": "Your balance is $10,000.00 USD."},
            ],
            "intent": "accounts",
        },
        {},
    )

    # Turn 1 in session 20 (different user / session)
    checkpointer.put(
        thread_session_20,
        {
            "messages": [
                {"role": "user", "content": "I need a cheque book."},
                {"role": "assistant", "content": "Cheque book request submitted."},
            ],
            "intent": "service",
        },
        {},
    )

    # Resume session 10 on Turn 2
    saved_state_10 = checkpointer.get_tuple(thread_session_10)
    assert saved_state_10 is not None
    history_10 = saved_state_10[0]["messages"]
    assert len(history_10) == 2
    assert history_10[0]["content"] == "What is my balance?"
    assert saved_state_10[0]["intent"] == "accounts"

    # Verify session 20 was unaffected
    saved_state_20 = checkpointer.get_tuple(thread_session_20)
    assert saved_state_20 is not None
    assert saved_state_20[0]["intent"] == "service"
    assert saved_state_20[0]["messages"][0]["content"] == "I need a cheque book."

