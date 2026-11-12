import os
from typing import Any

import httpx


def _get_django_config() -> tuple[str, str]:
    django_url = os.environ.get("DJANGO_API_URL", "http://backend:8000").rstrip("/")
    internal_key = os.environ.get("INTERNAL_API_KEY", "")
    if not internal_key:
        raise RuntimeError("INTERNAL_API_KEY is not configured.")
    return django_url, internal_key


async def _get_from_django(path: str, user_id: int) -> dict[str, Any]:
    django_url, internal_key = _get_django_config()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{django_url}{path}",
            headers={
                "X-Internal-Key": internal_key,
                "X-User-Id": str(user_id),
            },
        )
        response.raise_for_status()
        return response.json()


async def get_balance(user_id: int) -> dict[str, Any]:
    """Get the current bank account balance, account number, type, currency, and active status for a user."""
    return await _get_from_django("/internal/banking/balance/", user_id)


async def get_account_info(user_id: int) -> dict[str, Any]:
    """Get full bank account details including USD endorsement status, limit, holder name, and email for a user."""
    return await _get_from_django("/internal/banking/account-info/", user_id)

