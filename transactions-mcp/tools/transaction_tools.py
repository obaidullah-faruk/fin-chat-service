import os
from typing import Any

import httpx


def _get_django_config() -> tuple[str, str]:
    django_url = os.environ.get("DJANGO_API_URL", "http://backend:8000").rstrip("/")
    internal_key = os.environ.get("INTERNAL_API_KEY", "")
    if not internal_key:
        raise RuntimeError("INTERNAL_API_KEY is not configured.")
    return django_url, internal_key


async def _get_from_django(
    path: str,
    user_id: int,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    django_url, internal_key = _get_django_config()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{django_url}{path}",
            params=params or None,
            headers={
                "X-Internal-Key": internal_key,
                "X-User-Id": str(user_id),
            },
        )
        response.raise_for_status()
        return response.json()


async def get_transactions(
    user_id: int,
    limit: int = 10,
    transaction_type: str | None = None,
) -> dict[str, Any]:
    """Get recent transactions for a user's bank account, optionally filtered by transaction_type (deposit, withdrawal, transfer_in, transfer_out)."""
    params: dict[str, Any] = {"limit": limit}
    if transaction_type:
        params["transaction_type"] = transaction_type
    return await _get_from_django("/internal/banking/transactions/", user_id, params=params)


async def get_statement(
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Get an account statement summary and transactions for a user, optionally filtered by start_date and end_date (YYYY-MM-DD)."""
    params: dict[str, Any] = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return await _get_from_django("/internal/banking/statement/", user_id, params=params)

