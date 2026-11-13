from collections.abc import Sequence
from dataclasses import dataclass, field
import operator
import time
from typing import Annotated, Any, Literal, TypedDict

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
    from langchain_core.tools import BaseTool, ToolException
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages
    from langgraph.prebuilt import ToolNode, tools_condition
except ImportError:
    BaseChatModel = Any  # type: ignore[assignment,misc]
    AnyMessage = Any  # type: ignore[assignment,misc]
    HumanMessage = Any  # type: ignore[assignment,misc]
    SystemMessage = Any  # type: ignore[assignment,misc]
    BaseTool = Any  # type: ignore[assignment,misc]
    ToolException = Exception  # type: ignore[assignment,misc]
    ChatGoogleGenerativeAI = Any  # type: ignore[assignment,misc]
    END = "__end__"  # type: ignore[assignment,misc]
    START = "__start__"  # type: ignore[assignment,misc]
    StateGraph = Any  # type: ignore[assignment,misc]
    add_messages = lambda a, b: a + b  # type: ignore[assignment,misc]
    ToolNode = Any  # type: ignore[assignment,misc]
    tools_condition = Any  # type: ignore[assignment,misc]

from pydantic import BaseModel, Field

from agents.base import (
    CoordinatorResult,
    CoordinatorState,
    LLMCallTelemetry,
    TraceTelemetry,
    extract_message_text as _extract_message_text,
    extract_token_usage as _extract_token_usage,
    last_user_message_text as _last_user_message_text,
)
from config import Settings, get_settings
from mcp_client import get_user_mcp_tools
from security.authorization import (
    ROLE_PERMISSIONS,
    ToolAuthorizationError,
    check_tool_authorization,
    is_tool_allowed,
)

IntentLabel = Literal["accounts", "transactions", "service", "unknown"]

_INTENT_SYSTEM_PROMPT = """You are the routing coordinator for FinChat, a banking chatbot.
Your only job is to classify the user's message into one of these intents:
- "accounts": balance inquiry, account number, account status, account type, account details, USD endorsement info
- "transactions": transaction history, past transactions, deposits, withdrawals, transfers, statement request
- "service": cheque book request, change/update of address, KYC verification status, general banking service requests
- "unknown": anything that does not fit the banking intents above (greetings, casual chat, coding, general trivia)

Provide an accurate intent, confidence score between 0.0 and 1.0, and a one-sentence reason."""

_COORDINATOR_SYSTEM_PROMPT = """You are FinChat, a helpful, accurate banking assistant.
Detected intent: {intent}
User role: {role}
Account number: {account_number}

Rules:
1. Always call the appropriate tool(s) to retrieve real banking data or perform requested banking actions. Never fabricate balances, account numbers, transactions, or KYC statuses.
2. When a tool returns data, present the answer clearly, accurately, and concisely in plain language.
3. If a tool returns an error, explain the issue politely and tell the user what they can check or provide next."""

_FALLBACK_REPLY = (
    "I can help with FinChat banking requests such as checking your account balance and details, "
    "viewing recent transactions or statements, checking your KYC status, requesting a cheque book, "
    "or updating your address. How can I assist you today?"
)


class IntentClassification(BaseModel):
    intent: IntentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)


def create_gemini_llm(settings: Settings | None = None) -> ChatGoogleGenerativeAI:
    cfg = settings or get_settings()
    api_key = cfg.require_gemini_api_key()
    return ChatGoogleGenerativeAI(
        model=cfg.gemini_model,
        temperature=cfg.gemini_temperature,
        google_api_key=api_key,
    )


def build_coordinator_graph(
    *,
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    model_name: str = "gemini-3.8-flash",
):
    """Build and compile the Phase 3 single-coordinator LangGraph."""
    structured_classifier = llm.with_structured_output(
        IntentClassification,
        include_raw=True,
    )
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    tool_node = ToolNode(list(tools), handle_tool_errors=(ToolException,))

    async def classify_intent(state: CoordinatorState) -> dict[str, Any]:
        user_text = _last_user_message_text(state["messages"])
        started = time.perf_counter()
        result = await structured_classifier.ainvoke(
            [
                SystemMessage(content=_INTENT_SYSTEM_PROMPT),
                HumanMessage(content=user_text),
            ]
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        raw_msg: Any = None
        if isinstance(result, dict) and "parsed" in result:
            raw_msg = result.get("raw")
            parsed = result.get("parsed")
            if parsed is None:
                parsing_error = result.get("parsing_error")
                raise RuntimeError(f"Intent classification failed: {parsing_error}")
        elif isinstance(result, IntentClassification):
            parsed = result
        elif isinstance(result, dict):
            parsed = IntentClassification.model_validate(result)
        else:
            raise RuntimeError(f"Unexpected classifier output type: {type(result).__name__}")

        prompt_tokens, completion_tokens = _extract_token_usage(raw_msg)
        return {
            "intent": parsed.intent,
            "confidence": float(parsed.confidence),
            "reason": parsed.reason,
            "llm_calls": [
                LLMCallTelemetry(
                    node_name="classify_intent",
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                )
            ],
            "traces": [
                TraceTelemetry(
                    agent_name="classify_intent",
                    input_state={"message": user_text},
                    output_state={
                        "intent": parsed.intent,
                        "confidence": float(parsed.confidence),
                        "reason": parsed.reason,
                    },
                )
            ],
        }

    def route_by_intent(state: CoordinatorState) -> str:
        if state.get("intent") == "unknown":
            return "fallback"
        return "coordinator_agent"

    async def fallback_reply(state: CoordinatorState) -> dict[str, Any]:
        return {
            "reply": _FALLBACK_REPLY,
            "traces": [
                TraceTelemetry(
                    agent_name="fallback_reply",
                    input_state={"intent": state.get("intent", "unknown")},
                    output_state={"reply": _FALLBACK_REPLY},
                )
            ],
        }

    async def coordinator_agent(state: CoordinatorState) -> dict[str, Any]:
        system_prompt = _COORDINATOR_SYSTEM_PROMPT.format(
            intent=state.get("intent", "unknown"),
            role=state.get("role", "customer"),
            account_number=state.get("account_number") or "N/A",
        )
        started = time.perf_counter()
        response = await llm_with_tools.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]]
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        prompt_tokens, completion_tokens = _extract_token_usage(response)
        requested_tools = [
            tc["name"]
            for tc in (getattr(response, "tool_calls", None) or [])
            if isinstance(tc, dict) and tc.get("name")
        ]

        return {
            "messages": [response],
            "tools_called": requested_tools,
            "llm_calls": [
                LLMCallTelemetry(
                    node_name="coordinator_agent",
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                )
            ],
            "traces": [
                TraceTelemetry(
                    agent_name="coordinator_agent",
                    input_state={
                        "intent": state.get("intent"),
                        "message_count": len(state["messages"]),
                    },
                    output_state={
                        "tools_requested": requested_tools,
                        "has_final_text": bool(_extract_message_text(response.content)),
                    },
                )
            ],
        }

    async def finalize_reply(state: CoordinatorState) -> dict[str, Any]:
        last_message = state["messages"][-1]
        reply_text = _extract_message_text(getattr(last_message, "content", ""))
        if not reply_text:
            reply_text = "I completed your request, but could not generate a formatted response."
        return {
            "reply": reply_text,
            "traces": [
                TraceTelemetry(
                    agent_name="finalize_reply",
                    input_state={"tools_called": state.get("tools_called", [])},
                    output_state={"reply_length": len(reply_text)},
                )
            ],
        }

    graph = StateGraph(CoordinatorState)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("fallback_reply", fallback_reply)
    graph.add_node("coordinator_agent", coordinator_agent)
    graph.add_node("tools", tool_node)
    graph.add_node("finalize_reply", finalize_reply)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "fallback": "fallback_reply",
            "coordinator_agent": "coordinator_agent",
        },
    )
    graph.add_edge("fallback_reply", END)
    graph.add_conditional_edges(
        "coordinator_agent",
        tools_condition,
        {
            "tools": "tools",
            "__end__": "finalize_reply",
        },
    )
    graph.add_edge("tools", "coordinator_agent")
    graph.add_edge("finalize_reply", END)

    return graph.compile()


async def run_coordinator(
    *,
    message: str,
    user_id: int,
    role: str,
    session_id: int,
    account_number: str | None = None,
    tools: Sequence[BaseTool] | None = None,
    llm: BaseChatModel | None = None,
    settings: Settings | None = None,
) -> CoordinatorResult:
    """Execute the single-coordinator graph for one chat request."""
    cfg = settings or get_settings()
    model = llm or create_gemini_llm(cfg)
    active_tools = (
        list(tools)
        if tools is not None
        else await get_user_mcp_tools(user_id=user_id, role=role)
    )
    model_name = (
        getattr(model, "model", None)
        or getattr(model, "model_name", None)
        or cfg.gemini_model
    )

    compiled = build_coordinator_graph(
        llm=model,
        tools=active_tools,
        model_name=str(model_name),
    )

    final_state = await compiled.ainvoke(
        {
            "messages": [HumanMessage(content=message)],
            "user_id": user_id,
            "role": role,
            "account_number": account_number,
            "session_id": session_id,
            "intent": "",
            "confidence": 0.0,
            "reason": "",
            "reply": "",
            "tools_called": [],
            "llm_calls": [],
            "traces": [],
        },
        config={"recursion_limit": 12},
    )

    return CoordinatorResult(
        reply=final_state["reply"],
        intent=final_state["intent"],
        confidence=final_state["confidence"],
        reason=final_state["reason"],
        tools_called=final_state["tools_called"],
        llm_calls=final_state["llm_calls"],
        traces=final_state["traces"],
    )
