from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, HTTPException, status

from agents.coordinator import CoordinatorResult, run_coordinator
from db import (
    AIRepository,
    RunStatus,
    close_checkpointer,
    dispose_db,
    get_checkpointer,
    init_checkpointer,
    init_db,
)
from mcp_client import (
    ToolCallTelemetry,
    get_all_partitioned_mcp_tools,
    get_discovered_mcp_tools,
    get_user_mcp_tools,
)
from schemas.chat import ChatRequest, ChatResponse
from security.auth import verify_internal_caller
from security.pii_redactor import redact_pii
from streaming import StreamEventPublisher

logger = logging.getLogger("finchat.ai_service")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    try:
        await init_checkpointer()
    except Exception as exc:
        logger.warning("Checkpointer initialization warning: %s", exc)
    try:
        discovered = await get_discovered_mcp_tools()
        logger.info("Discovered %d MCP tool(s) on startup", len(discovered))
    except Exception as exc:
        logger.warning("Deferred MCP tool discovery on startup: %s", exc)
    yield
    await close_checkpointer()
    await dispose_db()


app = FastAPI(title="FinChat AI Service", version="0.1.0", lifespan=lifespan)


def get_ai_repository() -> AIRepository:
    return AIRepository()


async def _persist_run_telemetry(
    repo: AIRepository,
    *,
    run_id,
    result: CoordinatorResult,
    tool_telemetry: list[ToolCallTelemetry],
) -> None:
    for llm_call in result.llm_calls:
        await repo.log_llm_call(
            run_id=run_id,
            node_name=llm_call.node_name,
            model_name=llm_call.model_name,
            prompt_tokens=llm_call.prompt_tokens,
            completion_tokens=llm_call.completion_tokens,
            latency_ms=llm_call.latency_ms,
        )

    for tool_call in tool_telemetry:
        await repo.log_tool_call(
            run_id=run_id,
            tool_name=tool_call.tool_name,
            mcp_server=tool_call.mcp_server,
            input_json=tool_call.input_json,
            output_json=tool_call.output_json,
            latency_ms=tool_call.latency_ms,
            success=tool_call.success,
            error_message=tool_call.error_message,
        )

    for trace in result.traces:
        await repo.log_trace(
            run_id=run_id,
            agent_name=trace.agent_name,
            input_state=trace.input_state,
            output_state=trace.output_state,
        )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/chat/process",
    response_model=ChatResponse,
    dependencies=[Depends(verify_internal_caller)],
)
async def process_chat(
    payload: ChatRequest,
    repo: AIRepository = Depends(get_ai_repository),
) -> ChatResponse:
    run = await repo.create_run(
        session_id=payload.session_id,
        user_id=payload.user_id,
    )
    tool_telemetry: list[ToolCallTelemetry] = []
    publisher = StreamEventPublisher(session_id=payload.session_id)

    try:
        await publisher.publish_status("pii_scan", "Scanning message for sensitive data (PII)...")
        redaction = redact_pii(payload.message)
        if redaction.has_pii:
            await publisher.publish_status(
                "pii_redacted",
                f"Sensitive data ({len(redaction.entities)} entities) redacted for privacy.",
            )
            await repo.log_trace(
                run_id=run.id,
                agent_name="pii_redactor",
                input_state={"has_pii": True, "entity_count": len(redaction.entities)},
                output_state={
                    "masked_entities": [entity.entity_type for entity in redaction.entities]
                },
            )

        tools = await get_all_partitioned_mcp_tools(
            user_id=payload.user_id,
            role=payload.role,
            telemetry_records=tool_telemetry,
            publisher=publisher,
        )
        result = await run_coordinator(
            message=redaction.redacted_text,
            user_id=payload.user_id,
            role=payload.role,
            session_id=payload.session_id,
            account_number=payload.account_number,
            tools=tools,
            checkpointer=get_checkpointer(),
            publisher=publisher,
        )
        await _persist_run_telemetry(
            repo,
            run_id=run.id,
            result=result,
            tool_telemetry=tool_telemetry,
        )
        await repo.complete_run(
            run.id,
            status=RunStatus.COMPLETED,
            intent=result.intent,
        )
        await publisher.publish_done(
            reply=result.reply,
            tools_called=result.tools_called,
            intent=result.intent,
        )
    except Exception as exc:
        logger.exception(
            "AI processing failed: run_id=%s user_id=%s session_id=%s",
            run.id,
            payload.user_id,
            payload.session_id,
        )
        try:
            await publisher.publish_error(str(exc))
        except Exception:
            pass
        for tool_call in tool_telemetry:
            try:
                await repo.log_tool_call(
                    run_id=run.id,
                    tool_name=tool_call.tool_name,
                    mcp_server=tool_call.mcp_server,
                    input_json=tool_call.input_json,
                    output_json=tool_call.output_json,
                    latency_ms=tool_call.latency_ms,
                    success=tool_call.success,
                    error_message=tool_call.error_message,
                )
            except Exception:
                logger.warning("Failed to persist partial tool telemetry for run_id=%s", run.id)

        try:
            await repo.complete_run(
                run.id,
                status=RunStatus.FAILED,
                error_message=str(exc),
            )
        except Exception:
            logger.warning("Failed to mark run_id=%s as failed in ai-db", run.id)

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI processing failed: {exc}",
        ) from exc
    finally:
        try:
            await publisher.close()
        except Exception:
            pass

    return ChatResponse(
        reply=result.reply,
        tools_called=result.tools_called,
        intent=result.intent,
    )
