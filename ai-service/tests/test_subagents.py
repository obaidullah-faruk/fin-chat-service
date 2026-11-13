import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.accounts_agent import (
    ACCOUNTS_SYSTEM_PROMPT,
    create_accounts_agent_node,
)
from agents.base import (
    CoordinatorState,
    extract_message_text,
    extract_token_usage,
)
from agents.service_agent import (
    SERVICE_SYSTEM_PROMPT,
    create_service_agent_node,
)
from agents.transaction_agent import (
    TRANSACTION_SYSTEM_PROMPT,
    create_transaction_agent_node,
)
from mcp_client import (
    DiscoveredMCPTool,
    partition_mcp_tools_by_domain,
)


def _make_dummy_state(intent: str, message: str, role: str = "customer") -> CoordinatorState:
    mock_msg = SimpleNamespace(type="human", content=message)
    return {
        "messages": [mock_msg],  # type: ignore[list-item]
        "user_id": 4,
        "role": role,
        "account_number": "FC1000000001",
        "session_id": 10,
        "intent": intent,
        "confidence": 0.98,
        "reason": "Test reason",
        "reply": "",
        "tools_called": [],
        "llm_calls": [],
        "traces": [],
    }


def test_accounts_agent_node_execution():
    mock_llm = MagicMock()
    mock_response = SimpleNamespace(
        content="Your current balance is $10,000.00 USD.",
        tool_calls=[{"name": "get_balance", "args": {"user_id": 4}}],
        usage_metadata={"input_tokens": 50, "output_tokens": 20},
    )
    mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)

    node = create_accounts_agent_node(mock_llm, tools=[MagicMock()])
    state = _make_dummy_state("accounts", "What is my balance?")

    result = asyncio.run(node(state))

    assert len(result["messages"]) == 1
    assert result["tools_called"] == ["get_balance"]
    assert len(result["llm_calls"]) == 1
    assert result["llm_calls"][0].node_name == "accounts_agent"
    assert result["llm_calls"][0].prompt_tokens == 50
    assert result["llm_calls"][0].completion_tokens == 20
    assert len(result["traces"]) == 1
    assert result["traces"][0].agent_name == "accounts_agent"


def test_transaction_agent_node_execution():
    mock_llm = MagicMock()
    mock_response = SimpleNamespace(
        content="You have 3 recent transactions.",
        tool_calls=[{"name": "get_transactions", "args": {"user_id": 4, "limit": 5}}],
        usage_metadata={"input_tokens": 60, "output_tokens": 25},
    )
    mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)

    node = create_transaction_agent_node(mock_llm, tools=[MagicMock()])
    state = _make_dummy_state("transactions", "Show recent transactions")

    result = asyncio.run(node(state))

    assert len(result["messages"]) == 1
    assert result["tools_called"] == ["get_transactions"]
    assert len(result["llm_calls"]) == 1
    assert result["llm_calls"][0].node_name == "transaction_agent"
    assert result["traces"][0].agent_name == "transaction_agent"


def test_service_agent_node_execution():
    mock_llm = MagicMock()
    mock_response = SimpleNamespace(
        content="Your cheque book request for 25 leaves has been submitted.",
        tool_calls=[{"name": "request_cheque_book", "args": {"number_of_leaves": 25}}],
        usage_metadata={"input_tokens": 55, "output_tokens": 30},
    )
    mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)

    node = create_service_agent_node(mock_llm, tools=[MagicMock()])
    state = _make_dummy_state("service", "I want a new cheque book")

    result = asyncio.run(node(state))

    assert len(result["messages"]) == 1
    assert result["tools_called"] == ["request_cheque_book"]
    assert len(result["llm_calls"]) == 1
    assert result["llm_calls"][0].node_name == "service_agent"
    assert result["traces"][0].agent_name == "service_agent"


def test_transaction_agent_reference_lookup_execution():
    mock_llm = MagicMock()
    mock_response = SimpleNamespace(
        content="Transaction TXN-5E04875B25B1 was a branch teller deposit of $345.00 into account FC1000000001.",
        tool_calls=[{"name": "get_transaction_by_reference", "args": {"reference": "TXN-5E04875B25B1"}}],
        usage_metadata={"input_tokens": 70, "output_tokens": 35},
    )
    mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)

    node = create_transaction_agent_node(mock_llm, tools=[MagicMock()])
    state = _make_dummy_state("transactions", "Tell me about the TXN-5E04875B25B1")
    state["role"] = "superadmin"
    state["account_number"] = None

    result = asyncio.run(node(state))

    assert len(result["messages"]) == 1
    assert result["tools_called"] == ["get_transaction_by_reference"]
    assert "TXN-5E04875B25B1" in result["messages"][0].content
    assert result["llm_calls"][0].node_name == "transaction_agent"


def test_subagent_prompts_contain_required_context():
    formatted_acc = ACCOUNTS_SYSTEM_PROMPT.format(role="customer", account_number="FC1000000001")
    assert "Accounts Agent" in formatted_acc
    assert "FC1000000001" in formatted_acc
    assert "customer" in formatted_acc

    formatted_txn = TRANSACTION_SYSTEM_PROMPT.format(role="customer", account_number="FC1000000001")
    assert "Transaction Agent" in formatted_txn
    assert "get_transactions" in formatted_txn
    assert "get_transaction_by_reference" in formatted_txn

    formatted_svc = SERVICE_SYSTEM_PROMPT.format(role="customer", account_number="FC1000000001")
    assert "Service Agent" in formatted_svc
    assert "request_cheque_book" in formatted_svc
    assert "lookup_customer" in formatted_svc


def test_partition_mcp_tools_by_domain():
    discovered = [
        DiscoveredMCPTool(server_name="accounts", tool=MagicMock(name="get_balance")),
        DiscoveredMCPTool(server_name="accounts", tool=MagicMock(name="get_account_info")),
        DiscoveredMCPTool(server_name="accounts", tool=MagicMock(name="lookup_account")),
        DiscoveredMCPTool(server_name="accounts", tool=MagicMock(name="get_bank_dashboard_summary")),
        DiscoveredMCPTool(server_name="transactions", tool=MagicMock(name="get_transactions")),
        DiscoveredMCPTool(server_name="transactions", tool=MagicMock(name="get_statement")),
        DiscoveredMCPTool(server_name="transactions", tool=MagicMock(name="get_transaction_by_reference")),
        DiscoveredMCPTool(server_name="service", tool=MagicMock(name="request_cheque_book")),
        DiscoveredMCPTool(server_name="service", tool=MagicMock(name="update_address")),
        DiscoveredMCPTool(server_name="service", tool=MagicMock(name="get_kyc_status")),
        DiscoveredMCPTool(server_name="service", tool=MagicMock(name="lookup_customer")),
        DiscoveredMCPTool(server_name="service", tool=MagicMock(name="get_pending_reviews")),
    ]

    partitioned = partition_mcp_tools_by_domain(discovered)

    assert set(partitioned.keys()) == {"accounts", "transactions", "service"}
    assert len(partitioned["accounts"]) == 4
    assert len(partitioned["transactions"]) == 3
    assert len(partitioned["service"]) == 5


def test_extract_message_text_and_token_usage_helpers():
    # String extraction
    assert extract_message_text("  hello  ") == "hello"
    assert extract_message_text(None) == ""
    assert extract_message_text(["foo", {"text": "bar"}]) == "foo\nbar"

    # Token usage extraction
    msg_with_usage = SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 5})
    assert extract_token_usage(msg_with_usage) == (10, 5)

    msg_empty = SimpleNamespace()
    assert extract_token_usage(msg_empty) == (0, 0)

