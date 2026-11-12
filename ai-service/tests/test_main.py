import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from mcp_client import call_mcp_tool

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_process_chat_requires_valid_internal_key(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    payload = {
        "user_id": 1,
        "role": "customer",
        "account_number": "FC1000000001",
        "session_id": 10,
        "message": "What is my balance?",
    }

    missing_key_resp = client.post("/chat/process", json=payload)
    assert missing_key_resp.status_code == 403

    wrong_key_resp = client.post(
        "/chat/process",
        json=payload,
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert wrong_key_resp.status_code == 403


def test_process_chat_calls_get_balance_via_mcp(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    payload = {
        "user_id": 4,
        "role": "customer",
        "account_number": "FC1000000001",
        "session_id": 10,
        "message": "What is my balance?",
    }

    mock_balance = {
        "account_number": "FC1000000001",
        "account_type": "savings",
        "balance": "10000.00",
        "currency": "USD",
        "is_active": True,
    }

    with patch("main.call_mcp_tool", new=AsyncMock(return_value=mock_balance)) as mock_call:
        response = client.post(
            "/chat/process",
            json=payload,
            headers={"X-Internal-Key": "test-internal-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["tools_called"] == ["get_balance"]
    assert "FC1000000001" in data["reply"]
    assert "USD 10000.00" in data["reply"]
    mock_call.assert_awaited_once_with("accounts", "get_balance", {"user_id": 4})


def test_process_chat_routes_other_deterministic_queries(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    base_payload = {
        "user_id": 4,
        "role": "customer",
        "account_number": "FC1000000001",
        "session_id": 10,
    }

    with patch(
        "main.call_mcp_tool",
        new=AsyncMock(
            return_value={
                "account_number": "FC1000000001",
                "transactions": [
                    {
                        "transaction_type": "deposit",
                        "amount": "10000.00",
                        "reference": "TXN-123",
                        "description": "Opening deposit",
                    }
                ],
            }
        ),
    ) as mock_call:
        resp = client.post(
            "/chat/process",
            json={**base_payload, "message": "Show my recent transactions"},
            headers={"X-Internal-Key": "test-internal-key"},
        )
    assert resp.status_code == 200
    assert resp.json()["tools_called"] == ["get_transactions"]
    assert "TXN-123" in resp.json()["reply"]
    mock_call.assert_awaited_once_with("transactions", "get_transactions", {"user_id": 4, "limit": 5})

    with patch(
        "main.call_mcp_tool",
        new=AsyncMock(return_value={"username": "customer1", "kyc_status": "partial", "missing_fields": ["national_id"]}),
    ) as mock_call:
        resp = client.post(
            "/chat/process",
            json={**base_payload, "message": "Check my KYC status"},
            headers={"X-Internal-Key": "test-internal-key"},
        )
    assert resp.status_code == 200
    assert resp.json()["tools_called"] == ["get_kyc_status"]
    assert "partial" in resp.json()["reply"]
    mock_call.assert_awaited_once_with("service", "get_kyc_status", {"user_id": 4})


def test_process_chat_returns_502_on_mcp_failure(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    payload = {
        "user_id": 4,
        "role": "customer",
        "account_number": "FC1000000001",
        "session_id": 10,
        "message": "What is my balance?",
    }

    with patch("main.call_mcp_tool", new=AsyncMock(side_effect=RuntimeError("MCP down"))):
        response = client.post(
            "/chat/process",
            json=payload,
            headers={"X-Internal-Key": "test-internal-key"},
        )

    assert response.status_code == 502
    assert "MCP down" in response.json()["detail"]


def test_call_mcp_tool_extracts_data_and_handles_errors(monkeypatch):
    monkeypatch.setenv("ACCOUNTS_MCP_URL", "http://accounts-mcp:8002/mcp")

    mock_client = AsyncMock()
    mock_client.call_tool.return_value = SimpleNamespace(
        is_error=False,
        data={"account_number": "FC1000000001", "balance": "10000.00"},
        structured_content=None,
        content=[],
    )
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client

    with patch("mcp_client.Client", return_value=mock_client_cm) as mock_cls:
        result = asyncio.run(call_mcp_tool("accounts", "get_balance", {"user_id": 4}))

    mock_cls.assert_called_once_with("http://accounts-mcp:8002/mcp")
    mock_client.call_tool.assert_awaited_once_with("get_balance", {"user_id": 4})
    assert result == {"account_number": "FC1000000001", "balance": "10000.00"}

    with pytest.raises(ValueError, match="Unknown MCP server"):
        asyncio.run(call_mcp_tool("unknown", "get_balance", {"user_id": 4}))
