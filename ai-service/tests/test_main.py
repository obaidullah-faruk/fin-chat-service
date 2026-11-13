import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest
from sqlmodel import select

from agents.coordinator import CoordinatorResult, LLMCallTelemetry, TraceTelemetry
from db.models import AgentRun, AgentTrace, LLMCall, ToolCall
from db.repository import AIRepository
from db.session import create_db_engine, create_session_factory, init_db
from main import app, get_ai_repository
from mcp_client import ToolCallTelemetry, call_mcp_tool

client = TestClient(app)


async def _make_test_db():
    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    session_factory = create_session_factory(engine)
    return engine, session_factory, AIRepository(session_factory=session_factory)


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


def test_process_chat_runs_coordinator_and_logs_to_ai_db(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    engine, session_factory, repo = asyncio.run(_make_test_db())
    app.dependency_overrides[get_ai_repository] = lambda: repo

    async def fake_get_user_mcp_tools(*, user_id: int, telemetry_records=None, **_kwargs):
        assert user_id == 4
        if telemetry_records is not None:
            telemetry_records.append(
                ToolCallTelemetry(
                    tool_name="get_balance",
                    mcp_server="accounts",
                    input_json={"user_id": 4},
                    output_json={"account_number": "FC1000000001", "balance": "10000.00"},
                    latency_ms=42,
                    success=True,
                )
            )
        return []

    coordinator_result = CoordinatorResult(
        reply="Your savings account FC1000000001 has a balance of USD 10,000.00.",
        intent="accounts",
        confidence=0.99,
        reason="User asked for their balance.",
        tools_called=["get_balance"],
        llm_calls=[
            LLMCallTelemetry("classify_intent", "gemini-3.8-flash", 150, 40, 210),
            LLMCallTelemetry("coordinator_agent", "gemini-3.8-flash", 400, 60, 180),
        ],
        traces=[
            TraceTelemetry("classify_intent", {"message": "What is my balance?"}, {"intent": "accounts"}),
            TraceTelemetry("finalize_reply", {"tools_called": ["get_balance"]}, {"reply_length": 65}),
        ],
    )

    try:
        with (
            patch("main.get_user_mcp_tools", new=AsyncMock(side_effect=fake_get_user_mcp_tools)),
            patch("main.run_coordinator", new=AsyncMock(return_value=coordinator_result)),
        ):
            response = client.post(
                "/chat/process",
                json={
                    "user_id": 4,
                    "role": "customer",
                    "account_number": "FC1000000001",
                    "session_id": 10,
                    "message": "What is my balance?",
                },
                headers={"X-Internal-Key": "test-internal-key"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "accounts"
        assert data["tools_called"] == ["get_balance"]
        assert "10,000.00" in data["reply"]

        async def verify_db():
            async with session_factory() as session:
                runs = (await session.exec(select(AgentRun))).all()
                llm_rows = (await session.exec(select(LLMCall))).all()
                tool_rows = (await session.exec(select(ToolCall))).all()
                trace_rows = (await session.exec(select(AgentTrace))).all()
                return runs, llm_rows, tool_rows, trace_rows

        runs, llm_rows, tool_rows, trace_rows = asyncio.run(verify_db())
        assert len(runs) == 1
        assert runs[0].status == "completed"
        assert runs[0].intent == "accounts"
        assert runs[0].finished_at is not None
        assert len(llm_rows) == 2
        assert len(tool_rows) == 1
        assert tool_rows[0].tool_name == "get_balance"
        assert tool_rows[0].success is True
        assert len(trace_rows) == 2
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_process_chat_redacts_pii_and_logs_trace(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    engine, session_factory, repo = asyncio.run(_make_test_db())
    app.dependency_overrides[get_ai_repository] = lambda: repo

    captured_message = {}

    async def fake_run_coordinator(*, message: str, **kwargs):
        captured_message["message"] = message
        return CoordinatorResult(
            reply="Your balance is $1,000.00.",
            intent="accounts",
            confidence=0.99,
            reason="Balance inquiry",
            tools_called=["get_balance"],
            llm_calls=[],
            traces=[],
        )

    try:
        with (
            patch("main.get_user_mcp_tools", new=AsyncMock(return_value=[])),
            patch("main.run_coordinator", new=AsyncMock(side_effect=fake_run_coordinator)),
        ):
            response = client.post(
                "/chat/process",
                json={
                    "user_id": 4,
                    "role": "customer",
                    "account_number": "FC1000000001",
                    "session_id": 10,
                    "message": "My NID is 1234567890123 and phone 01712345678, what is my balance?",
                },
                headers={"X-Internal-Key": "test-internal-key"},
            )

        assert response.status_code == 200
        # The coordinator received sanitized message, not the raw PII!
        assert "1234567890123" not in captured_message["message"]
        assert "01712345678" not in captured_message["message"]
        assert "<ID_NUMBER>" in captured_message["message"]
        assert "<PHONE_NUMBER>" in captured_message["message"]

        async def verify_traces():
            async with session_factory() as session:
                return (await session.exec(select(AgentTrace))).all()

        traces = asyncio.run(verify_traces())
        pii_traces = [t for t in traces if t.agent_name == "pii_redactor"]
        assert len(pii_traces) == 1
        assert pii_traces[0].input_state.get("has_pii") is True
        assert pii_traces[0].input_state.get("entity_count") == 2
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_process_chat_logs_failed_run_and_returns_502_on_error(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    engine, session_factory, repo = asyncio.run(_make_test_db())
    app.dependency_overrides[get_ai_repository] = lambda: repo

    async def fake_get_user_mcp_tools(*, user_id: int, telemetry_records=None, **_kwargs):
        if telemetry_records is not None:
            telemetry_records.append(
                ToolCallTelemetry(
                    tool_name="get_balance",
                    mcp_server="accounts",
                    input_json={"user_id": user_id},
                    output_json={},
                    latency_ms=55,
                    success=False,
                    error_message="MCP down",
                )
            )
        return []

    try:
        with (
            patch("main.get_user_mcp_tools", new=AsyncMock(side_effect=fake_get_user_mcp_tools)),
            patch("main.run_coordinator", new=AsyncMock(side_effect=RuntimeError("MCP down"))),
        ):
            response = client.post(
                "/chat/process",
                json={
                    "user_id": 4,
                    "role": "customer",
                    "account_number": "FC1000000001",
                    "session_id": 10,
                    "message": "What is my balance?",
                },
                headers={"X-Internal-Key": "test-internal-key"},
            )

        assert response.status_code == 502
        assert "MCP down" in response.json()["detail"]

        async def verify_db():
            async with session_factory() as session:
                runs = (await session.exec(select(AgentRun))).all()
                tool_rows = (await session.exec(select(ToolCall))).all()
                return runs, tool_rows

        runs, tool_rows = asyncio.run(verify_db())
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert "MCP down" in (runs[0].error_message or "")
        assert len(tool_rows) == 1
        assert tool_rows[0].success is False
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


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
