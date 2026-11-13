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
    return build_agent_node(
        llm=llm,
        tools=tools,
        system_prompt_template=TRANSACTION_SYSTEM_PROMPT,
        node_name="transaction_agent",
        model_name=model_name,
    )
