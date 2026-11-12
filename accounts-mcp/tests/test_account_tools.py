import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from server import mcp
from tools.account_tools import get_account_info, get_balance


def test_health_route():
    app = mcp.http_app(path="/mcp")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "accounts-mcp"}


def test_mcp_registers_account_tools():
    tools = asyncio.run(mcp.get_tools())
    assert "get_balance" in tools
    assert "get_account_info" in tools


def test_get_balance_calls_django_internal_endpoint(monkeypatch):
    monkeypatch.setenv("DJANGO_API_URL", "http://backend:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-secret")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "account_number": "FC1000000001",
        "account_type": "savings",
        "balance": "10000.00",
        "currency": "USD",
        "is_active": True,
    }
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client

    with patch("tools.account_tools.httpx.AsyncClient", return_value=mock_client_cm):
        result = asyncio.run(get_balance(user_id=4))

    assert result["account_number"] == "FC1000000001"
    assert result["balance"] == "10000.00"
    mock_client.get.assert_awaited_once_with(
        "http://backend:8000/internal/banking/balance/",
        headers={"X-Internal-Key": "test-secret", "X-User-Id": "4"},
    )


def test_get_account_info_calls_django_internal_endpoint(monkeypatch):
    monkeypatch.setenv("DJANGO_API_URL", "http://backend:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-secret")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "account_number": "FC1000000001",
        "holder_name": "Alice Rahman",
        "is_usd_endorsed": False,
    }
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client

    with patch("tools.account_tools.httpx.AsyncClient", return_value=mock_client_cm):
        result = asyncio.run(get_account_info(user_id=4))

    assert result["holder_name"] == "Alice Rahman"
    mock_client.get.assert_awaited_once_with(
        "http://backend:8000/internal/banking/account-info/",
        headers={"X-Internal-Key": "test-secret", "X-User-Id": "4"},
    )


def test_missing_internal_key_raises(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        asyncio.run(get_balance(user_id=1))

