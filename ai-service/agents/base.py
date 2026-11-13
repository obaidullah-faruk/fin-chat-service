from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import logging
import operator
import time
from typing import Annotated, Any, TypedDict

logger = logging.getLogger("finchat.agents")

try:
    from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
    from langgraph.graph.message import add_messages
except ImportError:
    class BaseMessageStub:
        def __init__(self, content: Any = "", **kwargs: Any):
            self.content = content
            self.type = kwargs.get("type", "message")
            for k, v in kwargs.items():
                setattr(self, k, v)

    class HumanMessageStub(BaseMessageStub):
        def __init__(self, content: Any = "", **kwargs: Any):
            super().__init__(content=content, type="human", **kwargs)

    class SystemMessageStub(BaseMessageStub):
        def __init__(self, content: Any = "", **kwargs: Any):
            super().__init__(content=content, type="system", **kwargs)

    AnyMessage = BaseMessageStub  # type: ignore[assignment,misc]
    HumanMessage = HumanMessageStub  # type: ignore[assignment,misc]
    SystemMessage = SystemMessageStub  # type: ignore[assignment,misc]
    add_messages = lambda a, b: a + b  # type: ignore[assignment,misc]


@dataclass(slots=True)
class LLMCallTelemetry:
    node_name: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


@dataclass(slots=True)
class TraceTelemetry:
    agent_name: str
    input_state: dict[str, Any]
    output_state: dict[str, Any]


@dataclass(slots=True)
class CoordinatorResult:
    reply: str
    intent: str
    confidence: float
    reason: str
    tools_called: list[str] = field(default_factory=list)
    llm_calls: list[LLMCallTelemetry] = field(default_factory=list)
    traces: list[TraceTelemetry] = field(default_factory=list)


class CoordinatorState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: int
    role: str
    account_number: str | None
    session_id: int
    intent: str
    confidence: float
    reason: str
    reply: str
    tools_called: Annotated[list[str], operator.add]
    llm_calls: Annotated[list[LLMCallTelemetry], operator.add]
    traces: Annotated[list[TraceTelemetry], operator.add]


def extract_message_text(content: Any) -> str:
    """Extract plain text string from various LangChain message content formats."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(part for part in parts if part).strip()
    if content is None:
        return ""
    return str(content).strip()


def extract_token_usage(message: Any) -> tuple[int, int]:
    """Extract (prompt_tokens, completion_tokens) from LangChain response metadata."""
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        return (
            int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
            int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        )

    response_meta = getattr(message, "response_metadata", None)
    if isinstance(response_meta, dict):
        token_usage = response_meta.get("token_usage") or response_meta.get(
            "usage_metadata"
        )
        if isinstance(token_usage, dict):
            return (
                int(
                    token_usage.get("prompt_tokens")
                    or token_usage.get("input_tokens")
                    or 0
                ),
                int(
                    token_usage.get("completion_tokens")
                    or token_usage.get("output_tokens")
                    or 0
                ),
            )

    return 0, 0


def last_user_message_text(messages: Sequence[AnyMessage]) -> str:
    """Get content of the last HumanMessage in conversation."""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human" or type(msg).__name__ == "HumanMessage":
            return extract_message_text(getattr(msg, "content", ""))
    return extract_message_text(getattr(messages[-1], "content", "")) if messages else ""


def build_agent_node(
    *,
    llm: Any,
    tools: Sequence[Any],
    system_prompt_template: str,
    node_name: str,
    model_name: str = "gemini-3.8-flash",
) -> Callable[["CoordinatorState"], "dict[str, Any]"]:
    """
    Factory that builds a typed LangGraph agent node function.

    Eliminates the near-identical boilerplate in accounts_agent, transaction_agent,
    and service_agent by parametrising only what differs between them:
    - ``system_prompt_template``: An f-string template with ``{role}`` and
      ``{account_number}`` placeholders.
    - ``node_name``: Used for telemetry logging and the ``intent`` default.

    Returns an ``async`` callable suitable for ``graph.add_node()``.
    """
    llm_with_tools = llm.bind_tools(list(tools)) if tools and hasattr(llm, "bind_tools") else llm
    intent_default = node_name.replace("_agent", "")

    async def _agent_node(state: "CoordinatorState") -> "dict[str, Any]":
        system_prompt = system_prompt_template.format(
            role=state.get("role", "customer"),
            account_number=state.get("account_number") or "N/A",
        )
        started = time.perf_counter()
        logger.debug(
            "AGENT:invoke node=%s user_id=%s session_id=%s",
            node_name, state.get("user_id"), state.get("session_id"),
        )
        response = await llm_with_tools.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]]
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        prompt_tokens, completion_tokens = extract_token_usage(response)
        requested_tools = [
            tc["name"]
            for tc in (getattr(response, "tool_calls", None) or [])
            if isinstance(tc, dict) and tc.get("name")
        ]

        logger.info(
            "AGENT:done node=%s user_id=%s latency_ms=%d prompt_tokens=%d "
            "completion_tokens=%d tools_requested=%s",
            node_name, state.get("user_id"), latency_ms,
            prompt_tokens, completion_tokens, requested_tools,
        )

        return {
            "messages": [response],
            "tools_called": requested_tools,
            "llm_calls": [
                LLMCallTelemetry(
                    node_name=node_name,
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                )
            ],
            "traces": [
                TraceTelemetry(
                    agent_name=node_name,
                    input_state={
                        "intent": state.get("intent", intent_default),
                        "message_count": len(state["messages"]),
                    },
                    output_state={
                        "tools_requested": requested_tools,
                        "has_final_text": bool(
                            extract_message_text(getattr(response, "content", ""))
                        ),
                    },
                )
            ],
        }

    return _agent_node
