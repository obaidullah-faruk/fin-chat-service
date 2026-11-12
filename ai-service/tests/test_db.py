import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import uuid

import pytest
from sqlmodel import select

from db.models import AgentRun, AgentTrace, LLMCall, RunStatus, ToolCall
from db.repository import AIRepository
from db.session import create_db_engine, create_session_factory, init_db


def _run(coro):
    return asyncio.run(coro)


async def _make_repo():
    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    session_factory = create_session_factory(engine)
    return engine, session_factory, AIRepository(session_factory=session_factory)


def test_create_and_complete_run():
    async def scenario():
        engine, session_factory, repo = await _make_repo()
        try:
            run = await repo.create_run(session_id=7, user_id=42)
            assert run.id is not None
            assert run.session_id == 7
            assert run.user_id == 42
            assert run.status == RunStatus.RUNNING.value
            assert run.intent is None
            assert run.started_at is not None
            assert run.finished_at is None

            completed = await repo.complete_run(
                run.id,
                status=RunStatus.COMPLETED,
                intent="accounts",
            )
            assert completed.status == RunStatus.COMPLETED.value
            assert completed.intent == "accounts"
            assert completed.finished_at is not None
            assert completed.error_message is None

            async with session_factory() as session:
                stored = await session.get(AgentRun, run.id)
                assert stored is not None
                assert stored.status == "completed"
                assert stored.intent == "accounts"
        finally:
            await engine.dispose()

    _run(scenario())


def test_complete_run_failed_and_missing_run():
    async def scenario():
        engine, _, repo = await _make_repo()
        try:
            run = await repo.create_run(session_id=9, user_id=5)
            failed = await repo.complete_run(
                run.id,
                status=RunStatus.FAILED,
                error_message="Gemini timeout",
            )
            assert failed.status == "failed"
            assert failed.error_message == "Gemini timeout"
            assert failed.finished_at is not None

            with pytest.raises(ValueError, match="AgentRun not found"):
                await repo.complete_run(uuid.uuid4(), status=RunStatus.FAILED)
        finally:
            await engine.dispose()

    _run(scenario())


def test_log_llm_tool_and_trace_records():
    async def scenario():
        engine, session_factory, repo = await _make_repo()
        try:
            run = await repo.create_run(session_id=12, user_id=4, intent="accounts")

            llm_call = await repo.log_llm_call(
                run_id=run.id,
                node_name="classify_intent",
                model_name="gemini-2.0-flash",
                prompt_tokens=1000,
                completion_tokens=200,
                latency_ms=145,
            )
            assert llm_call.run_id == run.id
            assert llm_call.prompt_tokens == 1000
            assert llm_call.completion_tokens == 200
            assert llm_call.estimated_cost_usd == pytest.approx(0.000135)
            assert llm_call.latency_ms == 145

            explicit_llm_call = await repo.log_llm_call(
                run_id=run.id,
                node_name="coordinator_agent",
                model_name="gemini-2.0-flash",
                prompt_tokens=500,
                completion_tokens=100,
                estimated_cost_usd=0.0025,
                latency_ms=90,
            )
            assert explicit_llm_call.estimated_cost_usd == pytest.approx(0.0025)

            tool_ok = await repo.log_tool_call(
                run_id=run.id,
                tool_name="get_balance",
                mcp_server="accounts",
                input_json={"user_id": 4},
                output_json={
                    "balance": Decimal("5420.50"),
                    "checked_at": datetime(2026, 11, 12, tzinfo=timezone.utc),
                },
                latency_ms=38,
                success=True,
            )
            assert tool_ok.success is True
            assert tool_ok.output_json["balance"] == "5420.50"

            tool_err = await repo.log_tool_call(
                run_id=run.id,
                tool_name="get_statement",
                mcp_server="transactions",
                input_json={"user_id": 4},
                output_json={},
                latency_ms=502,
                success=False,
                error_message="Connection refused",
            )
            assert tool_err.success is False
            assert tool_err.error_message == "Connection refused"

            trace = await repo.log_trace(
                run_id=run.id,
                agent_name="coordinator",
                input_state={"message": "What is my balance?"},
                output_state={"intent": "accounts", "tools_called": ["get_balance"]},
            )
            assert trace.agent_name == "coordinator"
            assert trace.output_state["intent"] == "accounts"

            async with session_factory() as session:
                llm_rows = (
                    await session.exec(select(LLMCall).where(LLMCall.run_id == run.id))
                ).all()
                tool_rows = (
                    await session.exec(select(ToolCall).where(ToolCall.run_id == run.id))
                ).all()
                trace_rows = (
                    await session.exec(
                        select(AgentTrace).where(AgentTrace.run_id == run.id)
                    )
                ).all()

            assert len(llm_rows) == 2
            assert len(tool_rows) == 2
            assert len(trace_rows) == 1
        finally:
            await engine.dispose()

    _run(scenario())

