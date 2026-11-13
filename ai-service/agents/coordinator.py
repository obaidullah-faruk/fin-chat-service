from collections.abc import Sequence
from dataclasses import dataclass, field
import operator
import time
from typing import Annotated, Any, Literal, TypedDict

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
    from langchain_core.tools import BaseTool, ToolException
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langgraph.graph import END, START, StateGraph
    from langgraph.graph.message import add_messages
    from langgraph.prebuilt import ToolNode, tools_condition
except ImportError:
    BaseChatModel = Any  # type: ignore[assignment,misc]
    AIMessage = Any  # type: ignore[assignment,misc]
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

from agents.accounts_agent import create_accounts_agent_node
from agents.base import (
    CoordinatorResult,
    CoordinatorState,
    LLMCallTelemetry,
    TraceTelemetry,
    extract_message_text as _extract_message_text,
    extract_token_usage as _extract_token_usage,
    last_user_message_text as _last_user_message_text,
)
from agents.service_agent import create_service_agent_node
from agents.transaction_agent import create_transaction_agent_node
from config import Settings, get_settings
from mcp_client import (
    get_all_partitioned_mcp_tools,
    get_user_mcp_tools,
)
from security.authorization import (
    ROLE_PERMISSIONS,
    ToolAuthorizationError,
    check_tool_authorization,
    is_tool_allowed,
)

IntentLabel = Literal["accounts", "transactions", "service", "unknown"]

_INTENT_SYSTEM_PROMPT = """You are the routing coordinator for FinChat, an enterprise banking assistant.
Your only job is to classify the user's message into one of these intents based on the conversation context:
- "accounts": personal balance inquiry, account lookups by number/name (e.g., FC1000000001), account status/details, USD endorsement info, bank-wide institutional liquidity and operational metrics/aggregates, or explanations of account concepts.
- "transactions": personal transaction history, specific transaction lookups by reference ID (e.g., TXN-5E04875B25B1), deposits, withdrawals, transfers, account statements, transaction channels (e.g. Branch Teller, ATM, Online, POS), payment types, or follow-up explanations and clarifications regarding previously retrieved transactions or banking transaction terms.
- "service": cheque book requests, customer 360 profile lookups by name/username, pending approval review queries (cheques, endorsements), KYC status verification, change/update of address, general customer service workflows or follow-ups.
- "unknown": anything that does not fit the banking intents above (greetings, casual chat, coding, general trivia, poetry, non-banking questions).

Important Context Guidelines:
- Consider the conversation history: if the user asks a follow-up question (e.g., "What is branch teller actually is?", "Can you explain?", "What does that mean?"), classify the intent according to the banking topic discussed in the recent conversation turns.
- If the user asks a purely out-of-scope non-banking question (such as writing code, playing games, explaining general trivia unrelated to banking), classify as "unknown".

Provide an accurate intent, confidence score between 0.0 and 1.0, and a one-sentence reason."""

_COORDINATOR_SYSTEM_PROMPT = """You are FinChat, a helpful, accurate banking assistant.
Detected intent: {intent}
User role: {role}
Account number: {account_number}

Rules:
1. Always call the appropriate tool(s) to retrieve real banking data or perform requested banking actions. Never fabricate balances, account numbers, transactions, customer profiles, or KYC statuses.
2. Note on User Roles:
   - For retail customers (`customer`), assist with their personal accounts and transactions.
   - For administrative staff (`superadmin`, `admin`, `manager`), they do not have personal retail deposit accounts; assist them with cross-account lookups, transaction reference inquiries, customer 360 searches, and institutional summaries.
3. When a tool returns data, present the answer clearly, accurately, and concisely in plain language.
4. If a tool returns an error, explain the issue politely and tell the user what they can check or provide next."""

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


def _partition_tools(
    tools: Sequence[BaseTool] | dict[str, Sequence[BaseTool]] | None,
) -> dict[str, list[BaseTool]]:
    if isinstance(tools, dict):
        return {
            "accounts": list(tools.get("accounts", [])),
            "transactions": list(tools.get("transactions", [])),
            "service": list(tools.get("service", [])),
        }

    partitioned: dict[str, list[BaseTool]] = {
        "accounts": [],
        "transactions": [],
        "service": [],
    }
    if not tools:
        return partitioned

    accounts_tools = {
        "get_balance",
        "get_account_info",
        "lookup_account",
        "get_bank_dashboard_summary",
    }
    transactions_tools = {
        "get_transactions",
        "get_statement",
        "get_transaction_by_reference",
    }
    service_tools = {
        "request_cheque_book",
        "update_address",
        "get_kyc_status",
        "lookup_customer",
        "get_pending_reviews",
    }

    for t in tools:
        name = getattr(t, "name", "")
        if name in accounts_tools:
            partitioned["accounts"].append(t)
        elif name in transactions_tools:
            partitioned["transactions"].append(t)
        elif name in service_tools:
            partitioned["service"].append(t)
        else:
            server = getattr(t, "server_name", None)
            if server in partitioned:
                partitioned[server].append(t)
            else:
                partitioned["accounts"].append(t)

    return partitioned


def build_coordinator_graph(
    *,
    llm: BaseChatModel,
    tools: Sequence[BaseTool] | dict[str, Sequence[BaseTool]] | None = None,
    model_name: str = "gemini-3.8-flash",
    checkpointer: Any = None,
    publisher: Any = None,
):
    """Build and compile the Phase 4 multi-agent supervisor LangGraph."""
    structured_classifier = llm.with_structured_output(
        IntentClassification,
        include_raw=True,
    )
    partitioned = _partition_tools(tools)

    accounts_node = create_accounts_agent_node(
        llm=llm,
        tools=partitioned["accounts"],
        model_name=model_name,
    )
    accounts_tool_node = ToolNode(
        partitioned["accounts"],
        handle_tool_errors=(ToolException,),
    )

    transaction_node = create_transaction_agent_node(
        llm=llm,
        tools=partitioned["transactions"],
        model_name=model_name,
    )
    transaction_tool_node = ToolNode(
        partitioned["transactions"],
        handle_tool_errors=(ToolException,),
    )

    service_node = create_service_agent_node(
        llm=llm,
        tools=partitioned["service"],
        model_name=model_name,
    )
    service_tool_node = ToolNode(
        partitioned["service"],
        handle_tool_errors=(ToolException,),
    )

    async def classify_intent(state: CoordinatorState) -> dict[str, Any]:
        user_text = _last_user_message_text(state["messages"])
        started = time.perf_counter()

        if publisher is not None and hasattr(publisher, "publish_status"):
            try:
                await publisher.publish_status(
                    "routing",
                    "Analyzing request and selecting banking sub-agent...",
                )
            except Exception:
                pass

        dialogue_messages: list[AnyMessage] = []
        for m in state["messages"]:
            msg_type = getattr(m, "type", "")
            if msg_type in ("human", "ai") or isinstance(m, (HumanMessage, AIMessage)):
                text = _extract_message_text(getattr(m, "content", ""))
                if text:
                    if msg_type == "human" or isinstance(m, HumanMessage):
                        dialogue_messages.append(HumanMessage(content=text))
                    else:
                        dialogue_messages.append(AIMessage(content=text))

        recent_dialogue = dialogue_messages[-6:] if len(dialogue_messages) > 6 else dialogue_messages
        messages_for_classification = [
            SystemMessage(content=_INTENT_SYSTEM_PROMPT),
            *recent_dialogue,
        ]

        result = await structured_classifier.ainvoke(messages_for_classification)
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

        if publisher is not None and hasattr(publisher, "publish_status"):
            try:
                await publisher.publish_status(
                    "routed",
                    f"Routing request to {parsed.intent.title()} Agent ({parsed.confidence:.0%})...",
                    intent=parsed.intent,
                    confidence=float(parsed.confidence),
                )
            except Exception:
                pass

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
        intent = state.get("intent", "unknown")
        if intent == "accounts":
            return "accounts_agent"
        if intent == "transactions":
            return "transaction_agent"
        if intent == "service":
            return "service_agent"
        return "fallback_reply"

    async def fallback_reply(state: CoordinatorState) -> dict[str, Any]:
        if publisher is not None and hasattr(publisher, "publish_token"):
            words = _FALLBACK_REPLY.split(" ")
            for i, word in enumerate(words):
                chunk = word if i == len(words) - 1 else word + " "
                try:
                    await publisher.publish_token(chunk)
                except Exception:
                    pass
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

    async def finalize_reply(state: CoordinatorState) -> dict[str, Any]:
        last_message = state["messages"][-1]
        reply_text = _extract_message_text(getattr(last_message, "content", ""))
        if not reply_text:
            reply_text = "I completed your request, but could not generate a formatted response."
        if publisher is not None and hasattr(publisher, "publish_token"):
            words = reply_text.split(" ")
            for i, word in enumerate(words):
                chunk = word if i == len(words) - 1 else word + " "
                try:
                    await publisher.publish_token(chunk)
                except Exception:
                    pass
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

    # Sub-agent nodes & tool nodes
    graph.add_node("accounts_agent", accounts_node)
    graph.add_node("accounts_tools", accounts_tool_node)

    graph.add_node("transaction_agent", transaction_node)
    graph.add_node("transaction_tools", transaction_tool_node)

    graph.add_node("service_agent", service_node)
    graph.add_node("service_tools", service_tool_node)

    graph.add_node("finalize_reply", finalize_reply)

    # Supervisor routing edges
    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "accounts_agent": "accounts_agent",
            "transaction_agent": "transaction_agent",
            "service_agent": "service_agent",
            "fallback_reply": "fallback_reply",
        },
    )
    graph.add_edge("fallback_reply", END)

    # Accounts sub-agent loop
    graph.add_conditional_edges(
        "accounts_agent",
        tools_condition,
        {
            "tools": "accounts_tools",
            "__end__": "finalize_reply",
        },
    )
    graph.add_edge("accounts_tools", "accounts_agent")

    # Transaction sub-agent loop
    graph.add_conditional_edges(
        "transaction_agent",
        tools_condition,
        {
            "tools": "transaction_tools",
            "__end__": "finalize_reply",
        },
    )
    graph.add_edge("transaction_tools", "transaction_agent")

    # Service sub-agent loop
    graph.add_conditional_edges(
        "service_agent",
        tools_condition,
        {
            "tools": "service_tools",
            "__end__": "finalize_reply",
        },
    )
    graph.add_edge("service_tools", "service_agent")

    graph.add_edge("finalize_reply", END)

    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


async def run_coordinator(
    *,
    message: str,
    user_id: int,
    role: str,
    session_id: int,
    account_number: str | None = None,
    history: Sequence[Any] | None = None,
    tools: Sequence[BaseTool] | dict[str, Sequence[BaseTool]] | None = None,
    llm: BaseChatModel | None = None,
    settings: Settings | None = None,
    checkpointer: Any = None,
    publisher: Any = None,
) -> CoordinatorResult:
    """Execute the multi-agent coordinator graph for one chat request."""
    cfg = settings or get_settings()
    model = llm or create_gemini_llm(cfg)
    active_tools = (
        tools
        if tools is not None
        else await get_all_partitioned_mcp_tools(
            user_id=user_id,
            role=role,
            publisher=publisher,
        )
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
        checkpointer=checkpointer,
        publisher=publisher,
    )

    invoke_config: dict[str, Any] = {"recursion_limit": 12}
    if checkpointer is not None:
        invoke_config["configurable"] = {"thread_id": f"session_{session_id}"}

    initial_messages: list[AnyMessage] = []
    if history:
        for item in history:
            role_name = getattr(item, "role", None) or (item.get("role") if isinstance(item, dict) else None)
            content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else "")
            if not content:
                continue
            if role_name == "user":
                initial_messages.append(HumanMessage(content=content))
            elif role_name == "assistant":
                initial_messages.append(AIMessage(content=content))
    initial_messages.append(HumanMessage(content=message))

    final_state = await compiled.ainvoke(
        {
            "messages": initial_messages,
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
        config=invoke_config,
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
