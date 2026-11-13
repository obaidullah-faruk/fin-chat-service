from collections.abc import Sequence
import time
from typing import Any

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.tools import BaseTool
except ImportError:
    BaseChatModel = Any  # type: ignore[assignment,misc]
    BaseTool = Any  # type: ignore[assignment,misc]

from agents.base import (
    CoordinatorState,
    LLMCallTelemetry,
    SystemMessage,
    TraceTelemetry,
    extract_message_text,
    extract_token_usage,
)

SERVICE_SYSTEM_PROMPT = """You are FinChat's Service Agent, a specialized banking sub-agent.
Your sole focus is customer banking service requests: cheque book requests, address updates, and KYC verification status.
User role: {role}
Account number: {account_number}

Rules:
1. Always call the appropriate service tool (`request_cheque_book`, `update_address`, `get_kyc_status`) to execute service requests.
2. For cheque books, confirm the number of leaves requested (default 25 if unspecified).
3. If an authorization or permission error occurs (e.g. role 'customer' attempting 'update_address'), explain that this action requires manager or branch approval and guide the user on how to proceed.
4. Never fabricate request IDs, approval statuses, or confirmation codes.
"""


def create_service_agent_node(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    model_name: str = "gemini-3.8-flash",
):
    """Build the Service Agent LangGraph node with its dedicated tools bound."""
    llm_with_tools = llm.bind_tools(list(tools)) if tools and hasattr(llm, "bind_tools") else llm

    async def service_agent(state: CoordinatorState) -> dict[str, Any]:
        system_prompt = SERVICE_SYSTEM_PROMPT.format(
            role=state.get("role", "customer"),
            account_number=state.get("account_number") or "N/A",
        )
        started = time.perf_counter()
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

        return {
            "messages": [response],
            "tools_called": requested_tools,
            "llm_calls": [
                LLMCallTelemetry(
                    node_name="service_agent",
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                )
            ],
            "traces": [
                TraceTelemetry(
                    agent_name="service_agent",
                    input_state={
                        "intent": state.get("intent", "service"),
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

    return service_agent
