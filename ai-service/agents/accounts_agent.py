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

ACCOUNTS_SYSTEM_PROMPT = """You are FinChat's Accounts Agent, a specialized banking sub-agent.
Your sole focus is checking account balances, account numbers, account types, limits, and USD endorsement info.
User role: {role}
Account number: {account_number}

Rules:
1. Always call `get_balance` or `get_account_info` to retrieve real banking data. Never fabricate balances or account details.
2. Present balances clearly with currency (e.g. $10,000.00 USD).
3. If account data is not found or an error occurs, politely explain the issue and guide the user.
"""


def create_accounts_agent_node(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    model_name: str = "gemini-3.8-flash",
):
    """Build the Accounts Agent LangGraph node with its dedicated tools bound."""
    llm_with_tools = llm.bind_tools(list(tools)) if tools and hasattr(llm, "bind_tools") else llm

    async def accounts_agent(state: CoordinatorState) -> dict[str, Any]:
        system_prompt = ACCOUNTS_SYSTEM_PROMPT.format(
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
                    node_name="accounts_agent",
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                )
            ],
            "traces": [
                TraceTelemetry(
                    agent_name="accounts_agent",
                    input_state={
                        "intent": state.get("intent", "accounts"),
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

    return accounts_agent
