import json
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from db.models import AgentRun, AgentTrace, LLMCall, RunStatus, ToolCall, utcnow
from db.session import get_session_factory

# Default pricing per 1M tokens (USD) for Gemini Flash models.
_DEFAULT_INPUT_PRICE_PER_1M = 0.075
_DEFAULT_OUTPUT_PRICE_PER_1M = 0.30


def estimate_llm_cost_usd(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate USD cost for an LLM call from token counts."""
    _ = model_name  # Reserved for per-model pricing table later.
    input_cost = (max(prompt_tokens, 0) / 1_000_000) * _DEFAULT_INPUT_PRICE_PER_1M
    output_cost = (max(completion_tokens, 0) / 1_000_000) * _DEFAULT_OUTPUT_PRICE_PER_1M
    return round(input_cost + output_cost, 8)


def _to_json_safe(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    return json.loads(json.dumps(payload, default=str))


class AIRepository:
    """Async persistence layer for ai-db observability tables."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    async def create_run(
        self,
        *,
        session_id: int,
        user_id: int,
        intent: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            session_id=session_id,
            user_id=user_id,
            intent=intent,
            status=RunStatus.RUNNING.value,
        )
        async with self._session_factory() as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)
        return run

    async def complete_run(
        self,
        run_id: uuid.UUID,
        *,
        status: str | RunStatus = RunStatus.COMPLETED,
        intent: str | None = None,
        error_message: str | None = None,
    ) -> AgentRun:
        normalized_status = RunStatus(status).value
        async with self._session_factory() as session:
            run = await session.get(AgentRun, run_id)
            if run is None:
                raise ValueError(f"AgentRun not found: {run_id}")

            run.status = normalized_status
            run.finished_at = utcnow()
            if intent is not None:
                run.intent = intent
            if error_message is not None:
                run.error_message = error_message

            session.add(run)
            await session.commit()
            await session.refresh(run)
        return run

    async def log_llm_call(
        self,
        *,
        run_id: uuid.UUID,
        node_name: str,
        model_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated_cost_usd: float | None = None,
        latency_ms: int = 0,
    ) -> LLMCall:
        cost = (
            estimated_cost_usd
            if estimated_cost_usd is not None
            else estimate_llm_cost_usd(model_name, prompt_tokens, completion_tokens)
        )
        record = LLMCall(
            run_id=run_id,
            node_name=node_name,
            model_name=model_name,
            prompt_tokens=max(prompt_tokens, 0),
            completion_tokens=max(completion_tokens, 0),
            estimated_cost_usd=max(cost, 0.0),
            latency_ms=max(latency_ms, 0),
        )
        async with self._session_factory() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record

    async def log_tool_call(
        self,
        *,
        run_id: uuid.UUID,
        tool_name: str,
        mcp_server: str,
        input_json: dict[str, Any] | None = None,
        output_json: dict[str, Any] | None = None,
        latency_ms: int = 0,
        success: bool = True,
        error_message: str | None = None,
    ) -> ToolCall:
        record = ToolCall(
            run_id=run_id,
            tool_name=tool_name,
            mcp_server=mcp_server,
            input_json=_to_json_safe(input_json),
            output_json=_to_json_safe(output_json),
            latency_ms=max(latency_ms, 0),
            success=success,
            error_message=error_message,
        )
        async with self._session_factory() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record

    async def log_trace(
        self,
        *,
        run_id: uuid.UUID,
        agent_name: str,
        input_state: dict[str, Any] | None = None,
        output_state: dict[str, Any] | None = None,
    ) -> AgentTrace:
        record = AgentTrace(
            run_id=run_id,
            agent_name=agent_name,
            input_state=_to_json_safe(input_state),
            output_state=_to_json_safe(output_state),
        )
        async with self._session_factory() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record

