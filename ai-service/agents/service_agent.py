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
Your sole focus is banking service requests: cheque book requests, address updates, KYC verification status, customer 360 lookups, and reviewing pending managerial approval queues.
User role: {role}
Account number: {account_number}

Rules:
1. When a user requests a cheque book, call `request_cheque_book` confirming the number of leaves (default 25 if unspecified).
2. When a user requests an address update, call `update_address`.
3. When checking KYC verification status, call `get_kyc_status` (pass `target_user_id` if staff is inquiring about another customer).
4. When staff asks to look up a customer profile or contact info by name, username, or email, call `lookup_customer(query=...)`.
5. When staff asks about pending requests or items awaiting review/approval (cheques, USD endorsements), call `get_pending_reviews(review_type=...)`.
6. If an authorization error occurs (e.g., role 'customer' attempting staff actions), explain that this action requires manager or branch staff privileges.
7. Always call tools to retrieve or update real records. Never fabricate request IDs, approval statuses, customer profiles, or confirmation codes.
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
