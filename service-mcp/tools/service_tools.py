import os
from typing import Any

import httpx


def _get_django_config() -> tuple[str, str]:
    django_url = os.environ.get("DJANGO_API_URL", "http://backend:8000").rstrip("/")
    internal_key = os.environ.get("INTERNAL_API_KEY", "")
    if not internal_key:
        raise RuntimeError("INTERNAL_API_KEY is not configured.")
    return django_url, internal_key


async def _request_django(
    method: str,
    path: str,
    user_id: int,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    django_url, internal_key = _get_django_config()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(
            method,
            f"{django_url}{path}",
            json=json_body,
            headers={
                "X-Internal-Key": internal_key,
                "X-User-Id": str(user_id),
            },
        )
        response.raise_for_status()
        return response.json()


async def request_cheque_book(
    user_id: int,
    leaves_requested: int = 25,
    remarks: str = "",
    delivery_address_id: int | None = None,
) -> dict[str, Any]:
    """Submit a cheque book request for a user (leaves_requested must be 10, 25, 50, or 100)."""
    payload: dict[str, Any] = {
        "leaves_requested": leaves_requested,
        "remarks": remarks,
    }
    if delivery_address_id is not None:
        payload["delivery_address_id"] = delivery_address_id
    return await _request_django(
        "POST",
        "/internal/service/cheque-request/",
        user_id,
        json_body=payload,
    )


async def update_address(
    user_id: int,
    street: str,
    city: str,
    state: str,
    postal_code: str,
    country: str,
    label: str = "home",
    is_primary: bool = True,
    address_id: int | None = None,
) -> dict[str, Any]:
    """Create or update a user's residential/work address (label: home, work, or other)."""
    payload: dict[str, Any] = {
        "label": label,
        "street": street,
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "country": country,
        "is_primary": is_primary,
    }
    if address_id is not None:
        payload["address_id"] = address_id
    return await _request_django(
        "POST",
        "/internal/service/address/",
        user_id,
        json_body=payload,
    )


async def get_kyc_status(user_id: int) -> dict[str, Any]:
    """Get a user's KYC verification completeness status, endorsement state, and missing profile fields."""
    return await _request_django("GET", "/internal/service/kyc-status/", user_id)

