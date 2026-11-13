from collections.abc import Sequence
from typing import Any

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.tools import BaseTool
except ImportError:
    BaseChatModel = Any  # type: ignore[assignment,misc]
    BaseTool = Any  # type: ignore[assignment,misc]

from agents.base import build_agent_node

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
    return build_agent_node(
        llm=llm,
        tools=tools,
        system_prompt_template=ACCOUNTS_SYSTEM_PROMPT,
        node_name="accounts_agent",
        model_name=model_name,
    )
