from collections.abc import Sequence
from typing import Any

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.tools import BaseTool
except ImportError:
    BaseChatModel = Any  # type: ignore[assignment,misc]
    BaseTool = Any  # type: ignore[assignment,misc]

from agents.base import build_agent_node

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
    return build_agent_node(
        llm=llm,
        tools=tools,
        system_prompt_template=SERVICE_SYSTEM_PROMPT,
        node_name="service_agent",
        model_name=model_name,
    )
