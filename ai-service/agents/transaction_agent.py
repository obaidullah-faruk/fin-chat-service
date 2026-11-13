from collections.abc import Sequence
from typing import Any

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.tools import BaseTool
except ImportError:
    BaseChatModel = Any  # type: ignore[assignment,misc]
    BaseTool = Any  # type: ignore[assignment,misc]

from agents.base import build_agent_node

TRANSACTION_SYSTEM_PROMPT = """You are FinChat's Transaction Agent, a specialized banking sub-agent.
Your sole focus is retrieving transaction history, looking up specific transactions by reference, deposits, withdrawals, transfers, and account statements.
User role: {role}
Account number: {account_number}

Rules:
1. When the user asks about a specific transaction reference (e.g., TXN-5E04875B25B1), call `get_transaction_by_reference(reference=...)`.
2. When the user asks for personal recent transactions, call `get_transactions`. Note: For administrative staff without a personal retail account, explain that they do not hold personal retail records, but offer to look up any specific transaction by its reference.
3. If the user asks for a statement over a date range, pass start_date and end_date if provided to `get_statement`.
4. Always call tools to retrieve real records. Never invent transactions, amounts, dates, or references.
5. Present transactions clearly and neatly with reference, dates, amounts, type (Credit/Debit), channel, and descriptions.
6. If no transactions or records are found, inform the user clearly and politely.
"""


def create_transaction_agent_node(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
    model_name: str = "gemini-3.8-flash",
):
    """Build the Transaction Agent LangGraph node with its dedicated tools bound."""
    return build_agent_node(
        llm=llm,
        tools=tools,
        system_prompt_template=TRANSACTION_SYSTEM_PROMPT,
        node_name="transaction_agent",
        model_name=model_name,
    )
