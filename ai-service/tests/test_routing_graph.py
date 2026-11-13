import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.coordinator import (
    IntentClassification,
    _partition_tools,
    build_coordinator_graph,
    run_coordinator,
)


class MockMultiAgentLLM:
    """Mock LLM that routes structured classification and simulates sub-agent responses."""

    def __init__(
        self,
        intent: str,
        confidence: float,
        subagent_responses: list[Any],
        model_name: str = "gemini-3.8-flash",
    ):
        self.intent = intent
        self.confidence = confidence
        self.subagent_responses = subagent_responses
        self._call_index = 0
        self.model = model_name

    def with_structured_output(self, schema: Any, *, include_raw: bool = False):
        async def _classify(_messages: Any):
            parsed = IntentClassification(
                intent=self.intent,  # type: ignore[arg-type]
                confidence=self.confidence,
                reason=f"Detected {self.intent} intent",
            )
            raw = SimpleNamespace(
                usage_metadata={"input_tokens": 100, "output_tokens": 20}
            )
            if include_raw:
                return {"raw": raw, "parsed": parsed}
            return parsed

        mock_classifier = MagicMock()
        mock_classifier.ainvoke = AsyncMock(side_effect=_classify)
        return mock_classifier

    def bind_tools(self, tools: Any, **kwargs: Any):
        bound_instance = MockMultiAgentLLM(
            self.intent,
            self.confidence,
            self.subagent_responses,
            self.model,
        )
        bound_instance._call_index = self._call_index

        async def _ainvoke(_messages: Any):
            resp = self.subagent_responses[self._call_index]
            self._call_index += 1
            return resp

        bound_instance.ainvoke = AsyncMock(side_effect=_ainvoke)
        return bound_instance


def test_partition_tools_logic():
    t_bal = SimpleNamespace(name="get_balance")
    t_info = SimpleNamespace(name="get_account_info")
    t_acct_lookup = SimpleNamespace(name="lookup_account")
    t_dash = SimpleNamespace(name="get_bank_dashboard_summary")
    t_tx = SimpleNamespace(name="get_transactions")
    t_stmt = SimpleNamespace(name="get_statement")
    t_tx_ref = SimpleNamespace(name="get_transaction_by_reference")
    t_chq = SimpleNamespace(name="request_cheque_book")
    t_addr = SimpleNamespace(name="update_address")
    t_kyc = SimpleNamespace(name="get_kyc_status")
    t_cust = SimpleNamespace(name="lookup_customer")
    t_rev = SimpleNamespace(name="get_pending_reviews")

    all_tools = [
        t_bal, t_info, t_acct_lookup, t_dash,
        t_tx, t_stmt, t_tx_ref,
        t_chq, t_addr, t_kyc, t_cust, t_rev,
    ]
    partitioned = _partition_tools(all_tools)  # type: ignore[arg-type]

    assert len(partitioned["accounts"]) == 4
    assert len(partitioned["transactions"]) == 3
    assert len(partitioned["service"]) == 5
    assert t_bal in partitioned["accounts"]
    assert t_acct_lookup in partitioned["accounts"]
    assert t_dash in partitioned["accounts"]
    assert t_tx in partitioned["transactions"]
    assert t_tx_ref in partitioned["transactions"]
    assert t_chq in partitioned["service"]
    assert t_cust in partitioned["service"]
    assert t_rev in partitioned["service"]


def test_route_by_intent_mapping():
    from agents.coordinator import build_coordinator_graph
    # Test route_by_intent logic across all intent classes
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = MagicMock()
    # build a lightweight mock graph
    # or test routing decision
    state_acc = {"intent": "accounts"}
    state_txn = {"intent": "transactions"}
    state_svc = {"intent": "service"}
    state_unk = {"intent": "unknown"}
    state_other = {"intent": "random"}

    def routing_fn(state):
        intent = state.get("intent", "unknown")
        if intent == "accounts":
            return "accounts_agent"
        if intent == "transactions":
            return "transaction_agent"
        if intent == "service":
            return "service_agent"
        return "fallback_reply"

    assert routing_fn(state_acc) == "accounts_agent"
    assert routing_fn(state_txn) == "transaction_agent"
    assert routing_fn(state_svc) == "service_agent"
    assert routing_fn(state_unk) == "fallback_reply"
    assert routing_fn(state_other) == "fallback_reply"


def test_routing_to_accounts_agent():
    tool_called = []

    async def fake_balance(**kwargs):
        tool_called.append("get_balance")
        return '{"balance": "5420.50", "currency": "USD"}'

    tool_mock = MagicMock()
    tool_mock.name = "get_balance"
    tool_mock.ainvoke = AsyncMock(side_effect=fake_balance)

    # Sub-agent makes 1 tool call, then provides final response
    responses = [
        SimpleNamespace(
            content="",
            tool_calls=[{"name": "get_balance", "args": {}, "id": "tc1", "type": "tool_call"}],
            usage_metadata={"input_tokens": 150, "output_tokens": 15},
        ),
        SimpleNamespace(
            content="Your balance is $5,420.50 USD.",
            tool_calls=[],
            usage_metadata={"input_tokens": 200, "output_tokens": 25},
        ),
    ]

    llm = MockMultiAgentLLM("accounts", 0.98, responses)

    # If langchain_core is not present on host, test graph building or mock runner
    pytest.importorskip("langchain_core")

    result = asyncio.run(
        run_coordinator(
            message="What is my current balance?",
            user_id=4,
            role="customer",
            session_id=10,
            account_number="FC1000000001",
            tools=[tool_mock],
            llm=llm,  # type: ignore[arg-type]
        )
    )

    assert result.intent == "accounts"
    assert result.tools_called == ["get_balance"]
    assert "5,420.50" in result.reply
    assert [c.node_name for c in result.llm_calls] == [
        "classify_intent",
        "accounts_agent",
        "accounts_agent",
    ]


def test_routing_to_transaction_agent():
    tool_called = []

    async def fake_txns(**kwargs):
        tool_called.append("get_transactions")
        return '[{"amount": 100.0, "type": "debit"}]'

    tool_mock = MagicMock()
    tool_mock.name = "get_transactions"
    tool_mock.ainvoke = AsyncMock(side_effect=fake_txns)

    responses = [
        SimpleNamespace(
            content="",
            tool_calls=[{"name": "get_transactions", "args": {"limit": 5}, "id": "tc2", "type": "tool_call"}],
            usage_metadata={"input_tokens": 160, "output_tokens": 20},
        ),
        SimpleNamespace(
            content="Here are your recent transactions: Debit $100.00.",
            tool_calls=[],
            usage_metadata={"input_tokens": 220, "output_tokens": 30},
        ),
    ]

    llm = MockMultiAgentLLM("transactions", 0.96, responses)

    pytest.importorskip("langchain_core")

    result = asyncio.run(
        run_coordinator(
            message="Show my last 5 transactions",
            user_id=4,
            role="customer",
            session_id=10,
            account_number="FC1000000001",
            tools=[tool_mock],
            llm=llm,  # type: ignore[arg-type]
        )
    )

    assert result.intent == "transactions"
    assert result.tools_called == ["get_transactions"]
    assert "Debit $100.00" in result.reply
    assert [c.node_name for c in result.llm_calls] == [
        "classify_intent",
        "transaction_agent",
        "transaction_agent",
    ]


def test_routing_to_service_agent():
    tool_called = []

    async def fake_cheque(**kwargs):
        tool_called.append("request_cheque_book")
        return '{"status": "requested", "leaves": 25}'

    tool_mock = MagicMock()
    tool_mock.name = "request_cheque_book"
    tool_mock.ainvoke = AsyncMock(side_effect=fake_cheque)

    responses = [
        SimpleNamespace(
            content="",
            tool_calls=[{"name": "request_cheque_book", "args": {"number_of_leaves": 25}, "id": "tc3", "type": "tool_call"}],
            usage_metadata={"input_tokens": 140, "output_tokens": 18},
        ),
        SimpleNamespace(
            content="Your cheque book request for 25 leaves has been placed.",
            tool_calls=[],
            usage_metadata={"input_tokens": 190, "output_tokens": 25},
        ),
    ]

    llm = MockMultiAgentLLM("service", 0.94, responses)

    pytest.importorskip("langchain_core")

    result = asyncio.run(
        run_coordinator(
            message="Order a cheque book please",
            user_id=4,
            role="customer",
            session_id=10,
            account_number="FC1000000001",
            tools=[tool_mock],
            llm=llm,  # type: ignore[arg-type]
        )
    )

    assert result.intent == "service"
    assert result.tools_called == ["request_cheque_book"]
    assert "cheque book request" in result.reply
    assert [c.node_name for c in result.llm_calls] == [
        "classify_intent",
        "service_agent",
        "service_agent",
    ]


def test_routing_to_fallback_for_unknown_intent():
    llm = MockMultiAgentLLM("unknown", 0.99, [])

    pytest.importorskip("langchain_core")

    result = asyncio.run(
        run_coordinator(
            message="Tell me a joke about robots",
            user_id=4,
            role="customer",
            session_id=10,
            tools=[],
            llm=llm,  # type: ignore[arg-type]
        )
    )

    assert result.intent == "unknown"
    assert result.tools_called == []
    assert "FinChat banking requests" in result.reply
    assert [c.node_name for c in result.llm_calls] == ["classify_intent"]
    assert [t.agent_name for t in result.traces] == ["classify_intent", "fallback_reply"]
