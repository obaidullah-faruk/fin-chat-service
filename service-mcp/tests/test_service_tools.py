import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from server import mcp
from tools.service_tools import get_kyc_status, request_cheque_book, update_address


def test_health_route():
    app = mcp.http_app(path="/mcp")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "service-mcp"}


def test_mcp_registers_service_tools():
    tools = asyncio.run(mcp.get_tools())
    assert "request_cheque_book" in tools
    assert "update_address" in tools
    assert "get_kyc_status" in tools


def test_request_cheque_book_calls_django_internal_endpoint(monkeypatch):
    monkeypatch.setenv("DJANGO_API_URL", "http://backend:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-secret")

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 1, "leaves_requested": 25, "status": "pending"}
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client

    with patch("tools.service_tools.httpx.AsyncClient", return_value=mock_client_cm):
        result = asyncio.run(request_cheque_book(user_id=4, leaves_requested=25, remarks="Needed soon"))

    assert result["status"] == "pending"
    mock_client.request.assert_awaited_once_with(
        "POST",
        "http://backend:8000/internal/service/cheque-request/",
        json={"leaves_requested": 25, "remarks": "Needed soon"},
        headers={"X-Internal-Key": "test-secret", "X-User-Id": "4"},
    )


def test_update_address_calls_django_internal_endpoint(monkeypatch):
    monkeypatch.setenv("DJANGO_API_URL", "http://backend:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-secret")

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": 2, "street": "10 Lake Road", "is_primary": True}
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client

    with patch("tools.service_tools.httpx.AsyncClient", return_value=mock_client_cm):
        result = asyncio.run(
            update_address(
                user_id=4,
                street="10 Lake Road",
                city="Dhaka",
                state="Dhaka",
                postal_code="1212",
                country="Bangladesh",
            )
        )

    assert result["street"] == "10 Lake Road"
    mock_client.request.assert_awaited_once_with(
        "POST",
        "http://backend:8000/internal/service/address/",
        json={
            "label": "home",
            "street": "10 Lake Road",
            "city": "Dhaka",
            "state": "Dhaka",
            "postal_code": "1212",
            "country": "Bangladesh",
            "is_primary": True,
        },
        headers={"X-Internal-Key": "test-secret", "X-User-Id": "4"},
    )


def test_get_kyc_status_calls_django_internal_endpoint(monkeypatch):
    monkeypatch.setenv("DJANGO_API_URL", "http://backend:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-secret")

    mock_response = MagicMock()
    mock_response.json.return_value = {"username": "customer1", "kyc_status": "partial"}
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.request.return_value = mock_response
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client

    with patch("tools.service_tools.httpx.AsyncClient", return_value=mock_client_cm):
        result = asyncio.run(get_kyc_status(user_id=4))

    assert result["kyc_status"] == "partial"
    mock_client.request.assert_awaited_once_with(
        "GET",
        "http://backend:8000/internal/service/kyc-status/",
        json=None,
        headers={"X-Internal-Key": "test-secret", "X-User-Id": "4"},
    )


def test_missing_internal_key_raises(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        asyncio.run(get_kyc_status(user_id=1))

