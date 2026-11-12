import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from server import mcp
from tools.transaction_tools import get_statement, get_transactions


def test_health_route():
    app = mcp.http_app(path="/mcp")
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "transactions-mcp"}


def test_mcp_registers_transaction_tools():
    tools = asyncio.run(mcp.get_tools())
    assert "get_transactions" in tools
    assert "get_statement" in tools


def test_get_transactions_calls_django_internal_endpoint(monkeypatch):
    monkeypatch.setenv("DJANGO_API_URL", "http://backend:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-secret")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "account_number": "FC1000000001",
        "count": 1,
        "transactions": [{"id": 1, "transaction_type": "deposit", "amount": "10000.00"}],
    }
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client

    with patch("tools.transaction_tools.httpx.AsyncClient", return_value=mock_client_cm):
        result = asyncio.run(get_transactions(user_id=4, limit=5, transaction_type="deposit"))

    assert result["count"] == 1
    mock_client.get.assert_awaited_once_with(
        "http://backend:8000/internal/banking/transactions/",
        params={"limit": 5, "transaction_type": "deposit"},
        headers={"X-Internal-Key": "test-secret", "X-User-Id": "4"},
    )


def test_get_statement_calls_django_internal_endpoint(monkeypatch):
    monkeypatch.setenv("DJANGO_API_URL", "http://backend:8000")
    monkeypatch.setenv("INTERNAL_API_KEY", "test-secret")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "account": {"account_number": "FC1000000001"},
        "period": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
        "summary": {"transaction_count": 1},
        "transactions": [],
    }
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client

    with patch("tools.transaction_tools.httpx.AsyncClient", return_value=mock_client_cm):
        result = asyncio.run(
            get_statement(user_id=4, start_date="2026-01-01", end_date="2026-01-31")
        )

    assert result["period"]["start_date"] == "2026-01-01"
    mock_client.get.assert_awaited_once_with(
        "http://backend:8000/internal/banking/statement/",
        params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        headers={"X-Internal-Key": "test-secret", "X-User-Id": "4"},
    )


def test_missing_internal_key_raises(monkeypatch):
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        asyncio.run(get_transactions(user_id=1))

