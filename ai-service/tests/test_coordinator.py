import asyncio
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool, StructuredTool, ToolException
import pytest

from agents.coordinator import (
    IntentClassification,
    create_gemini_llm,
    run_coordinator,
)
from config import Settings


class FakeCoordinatorLLM(BaseChatModel):
    """Deterministic async fake chat model supporting structured output and tool binding."""

    intent_result: IntentClassification
    agent_responses: list[AIMessage]
    _call_index: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake-gemini"

    @property
    def model(self) -> str:
        return "gemini-2.0-flash"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("Use async invocation in tests")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        msg = self.agent_responses[self._call_index]
        self._call_index += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> "FakeCoordinatorLLM":
        return self

    def with_structured_output(
        self,
        schema: Any,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ):
        async def _classify(_input: Any):
            raw = AIMessage(
                content="",
                usage_metadata={
                    "input_tokens": 110,
                    "output_tokens": 25,
                    "total_tokens": 135,
                },
            )
            if include_raw:
                return {"raw": raw, "parsed": self.intent_result, "parsing_error": None}
            return self.intent_result

        return RunnableLambda(_classify)


def test_coordinator_accounts_flow_calls_tool_and_formats_reply():
    tool_calls_seen: list[dict[str, Any]] = []

    async def fake_get_balance() -> str:
        tool_calls_seen.append({"called": True})
        return '{"account_number": "FC1000000001", "balance": "10000.00", "currency": "USD"}'

    balance_tool = StructuredTool.from_function(
        coroutine=fake_get_balance,
        name="get_balance",
        description="Get account balance",
        args_schema={"type": "object", "properties": {}, "required": []},
    )

    fake_llm = FakeCoordinatorLLM(
        intent_result=IntentClassification(
            intent="accounts",
            confidence=0.98,
            reason="User is asking for their account balance.",
        ),
        agent_responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_balance",
                        "args": {},
                        "id": "call_bal_1",
                        "type": "tool_call",
                    }
                ],
                usage_metadata={"input_tokens": 180, "output_tokens": 20, "total_tokens": 200},
            ),
            AIMessage(
                content="Your savings account FC1000000001 has a balance of USD 10,000.00.",
                usage_metadata={"input_tokens": 240, "output_tokens": 30, "total_tokens": 270},
            ),
        ],
    )

    result = asyncio.run(
        run_coordinator(
            message="What is my balance?",
            user_id=4,
            role="customer",
            session_id=10,
            account_number="FC1000000001",
            tools=[balance_tool],
            llm=fake_llm,
        )
    )

    assert tool_calls_seen == [{"called": True}]
    assert result.intent == "accounts"
    assert result.confidence == pytest.approx(0.98)
    assert result.tools_called == ["get_balance"]
    assert "FC1000000001" in result.reply
    assert "10,000.00" in result.reply
    assert [c.node_name for c in result.llm_calls] == [
        "classify_intent",
        "coordinator_agent",
        "coordinator_agent",
    ]
    assert sum(c.prompt_tokens for c in result.llm_calls) == 530
    assert sum(c.completion_tokens for c in result.llm_calls) == 75
    assert [t.agent_name for t in result.traces] == [
        "classify_intent",
        "coordinator_agent",
        "coordinator_agent",
        "finalize_reply",
    ]


def test_coordinator_unknown_intent_routes_to_fallback_without_tools():
    async def should_not_run() -> str:
        raise AssertionError("Tool should not be called for unknown intent")

    balance_tool = StructuredTool.from_function(
        coroutine=should_not_run,
        name="get_balance",
        description="Get account balance",
        args_schema={"type": "object", "properties": {}, "required": []},
    )

    fake_llm = FakeCoordinatorLLM(
        intent_result=IntentClassification(
            intent="unknown",
            confidence=0.95,
            reason="Greeting or general request unrelated to banking.",
        ),
        agent_responses=[],
    )

    result = asyncio.run(
        run_coordinator(
            message="Write me a haiku about clouds",
            user_id=4,
            role="customer",
            session_id=10,
            tools=[balance_tool],
            llm=fake_llm,
        )
    )

    assert result.intent == "unknown"
    assert result.tools_called == []
    assert "FinChat banking requests" in result.reply
    assert [c.node_name for c in result.llm_calls] == ["classify_intent"]
    assert [t.agent_name for t in result.traces] == ["classify_intent", "fallback_reply"]


def test_coordinator_handles_tool_exception_and_list_content():
    async def failing_balance() -> str:
        raise ToolException("Account not found for user")

    balance_tool = StructuredTool.from_function(
        coroutine=failing_balance,
        name="get_balance",
        description="Get account balance",
        args_schema={"type": "object", "properties": {}, "required": []},
    )

    fake_llm = FakeCoordinatorLLM(
        intent_result=IntentClassification(
            intent="accounts",
            confidence=0.9,
            reason="Balance request.",
        ),
        agent_responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_balance", "args": {}, "id": "call_err_1", "type": "tool_call"}
                ],
                usage_metadata={"input_tokens": 120, "output_tokens": 15, "total_tokens": 135},
            ),
            AIMessage(
                content=[
                    {"type": "text", "text": "I could not find an active bank account for your profile."}
                ],
                usage_metadata={"input_tokens": 160, "output_tokens": 18, "total_tokens": 178},
            ),
        ],
    )

    result = asyncio.run(
        run_coordinator(
            message="What is my balance?",
            user_id=999,
            role="customer",
            session_id=11,
            tools=[balance_tool],
            llm=fake_llm,
        )
    )

    assert result.tools_called == ["get_balance"]
    assert result.reply == "I could not find an active bank account for your profile."


def test_coordinator_propagates_unexpected_transport_errors():
    async def broken_transport() -> str:
        raise RuntimeError("MCP server unreachable")

    balance_tool = StructuredTool.from_function(
        coroutine=broken_transport,
        name="get_balance",
        description="Get account balance",
        args_schema={"type": "object", "properties": {}, "required": []},
    )

    fake_llm = FakeCoordinatorLLM(
        intent_result=IntentClassification(
            intent="accounts",
            confidence=0.95,
            reason="Balance request.",
        ),
        agent_responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_balance", "args": {}, "id": "call_fail_1", "type": "tool_call"}
                ],
            ),
        ],
    )

    with pytest.raises(RuntimeError, match="MCP server unreachable"):
        asyncio.run(
            run_coordinator(
                message="What is my balance?",
                user_id=4,
                role="customer",
                session_id=10,
                tools=[balance_tool],
                llm=fake_llm,
            )
        )


def test_create_gemini_llm_validates_key_and_configures_model():
    missing_settings = Settings(GEMINI_API_KEY="Create_key")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        create_gemini_llm(missing_settings)

    valid_settings = Settings(
        GEMINI_API_KEY="AIza-fake-test-key",
        GEMINI_MODEL="gemini-3.8-flash",
        GEMINI_TEMPERATURE=0.1,
    )
    llm = create_gemini_llm(valid_settings)
    assert llm.model.endswith("gemini-3.8-flash")
    assert llm.temperature == pytest.approx(0.1)
