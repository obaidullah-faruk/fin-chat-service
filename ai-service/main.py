import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status

from mcp_client import call_mcp_tool
from schemas.chat import ChatRequest, ChatResponse
from security.auth import verify_internal_caller

logger = logging.getLogger("finchat.ai_service")

app = FastAPI(title="FinChat AI Service", version="0.1.0")


def _select_hardcoded_tool(payload: ChatRequest) -> tuple[str, str, dict[str, Any]]:
    """Deterministic Phase 2 tool selector (no LLM yet)."""
    lowered = payload.message.lower()
    if "account info" in lowered or "account detail" in lowered or "endorsement" in lowered:
        return "accounts", "get_account_info", {"user_id": payload.user_id}
    if "statement" in lowered:
        return "transactions", "get_statement", {"user_id": payload.user_id}
    if "transaction" in lowered or "history" in lowered:
        return "transactions", "get_transactions", {"user_id": payload.user_id, "limit": 5}
    if "kyc" in lowered:
        return "service", "get_kyc_status", {"user_id": payload.user_id}
    return "accounts", "get_balance", {"user_id": payload.user_id}


def _format_tool_reply(tool_name: str, data: dict[str, Any]) -> str:
    if tool_name == "get_balance":
        status_label = "active" if data.get("is_active") else "frozen"
        return (
            f"Your {data.get('account_type', 'bank')} account "
            f"({data.get('account_number', 'N/A')}) has a balance of "
            f"{data.get('currency', 'USD')} {data.get('balance', '0.00')} "
            f"(status: {status_label})."
        )

    if tool_name == "get_account_info":
        endorsed = "enabled" if data.get("is_usd_endorsed") else "not enabled"
        return (
            f"Account {data.get('account_number', 'N/A')} ({data.get('account_type', 'N/A')}) "
            f"for {data.get('holder_name', 'N/A')}: balance {data.get('currency', 'USD')} "
            f"{data.get('balance', '0.00')}, USD endorsement {endorsed} "
            f"(limit: {data.get('usd_endorsement_limit', '0.00')})."
        )

    if tool_name == "get_transactions":
        txns = data.get("transactions", [])
        if not txns:
            return f"No recent transactions found for account {data.get('account_number', 'N/A')}."
        lines = [
            f"- {t.get('transaction_type')} {t.get('amount')} ({t.get('reference')}): {t.get('description')}"
            for t in txns[:5]
        ]
        return (
            f"Recent transactions for account {data.get('account_number', 'N/A')}:\n"
            + "\n".join(lines)
        )

    if tool_name == "get_statement":
        account = data.get("account", {})
        summary = data.get("summary", {})
        return (
            f"Statement for account {account.get('account_number', 'N/A')}: "
            f"{summary.get('transaction_count', 0)} transaction(s), "
            f"deposits {summary.get('total_deposits', '0.00')}, "
            f"withdrawals {summary.get('total_withdrawals', '0.00')}."
        )

    if tool_name == "get_kyc_status":
        missing = data.get("missing_fields") or []
        missing_text = ", ".join(missing) if missing else "none"
        return (
            f"KYC status for {data.get('username', 'user')}: {data.get('kyc_status', 'unknown')} "
            f"(missing fields: {missing_text})."
        )

    return f"Tool {tool_name} result: {data}"


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/chat/process",
    response_model=ChatResponse,
    dependencies=[Depends(verify_internal_caller)],
)
async def process_chat(payload: ChatRequest) -> ChatResponse:
    server_name, tool_name, arguments = _select_hardcoded_tool(payload)
    try:
        tool_data = await call_mcp_tool(server_name, tool_name, arguments)
    except Exception as exc:
        logger.exception(
            "MCP tool invocation failed: server=%s tool=%s user_id=%s",
            server_name,
            tool_name,
            payload.user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP tool invocation failed: {exc}",
        ) from exc

    return ChatResponse(
        reply=_format_tool_reply(tool_name, tool_data),
        tools_called=[tool_name],
    )
