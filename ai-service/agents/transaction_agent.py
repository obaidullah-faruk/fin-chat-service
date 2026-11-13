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

TRANSACTION_SYSTEM_PROMPT = """You are FinChat's Transaction Agent, a specialized banking sub-agent.
Your sole focus is retrieving transaction history, deposits, withdrawals, transfers, and account statements.
User role: {role}
Account number: {account_number}

Rules:
1. Always call `get_transactions` or `get_statement` to retrieve real records. Never invent transactions, amounts, or dates.
2. Present transactions clearly and neatly with dates, amounts, type (Credit/Debit), and descriptions.
3. If the user asks for a statement over a date range, pass start_date and end_date if provided.
4. If no transactions are found, inform the user clearly and politely.
"""


def create_transaction_agent_node(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    model_name: str = "gemini-3.8-flash",
):
    """Build the Transaction Agent LangGraph node with its dedicated tools bound."""
    llm_with_tools = llm.bind_tools(list(tools)) if tools and hasattr(llm, "bind_tools") else llm

    async def transaction_agent(state: CoordinatorState) -> dict[str, Any]:
        system_prompt = TRANSACTION_SYSTEM_PROMPT.format(
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
                    node_name="transaction_agent",
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                )
            ],
            "traces": [
                TraceTelemetry(
                    agent_name="transaction_agent",
                    input_state={
                        "intent": state.get("intent", "transactions"),
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

    return transaction_agent
