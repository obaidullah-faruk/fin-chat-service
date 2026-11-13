import asyncio
import time
import warnings
warnings.filterwarnings("ignore")

from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, HTTPException, Request, status

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
from security.pii_redactor import DEFAULT_REPLACEMENTS, redact_pii
from streaming import StreamEventPublisher

logger = logging.getLogger("finchat.ai_service")

# ---------------------------------------------------------------------------
# Guardrail constants
# ---------------------------------------------------------------------------
_MAX_MESSAGE_LENGTH = 2_000   # Hard cap on inbound message size (chars)
_REQUEST_TIMEOUT_SEC = 90     # Wall-clock cap for the full coordinator run


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    try:
        await init_checkpointer()
    except Exception as exc:
        logger.warning("Checkpointer initialization warning: %s", exc)
    try:
        discovered = await get_discovered_mcp_tools()
        logger.info(
            "Startup: discovered %d MCP tool(s) across %d server(s)",
            len(discovered),
            len({t.server_name for t in discovered}),
        )
    except Exception as exc:
        logger.warning("Deferred MCP tool discovery on startup: %s", exc)
    yield
    await close_checkpointer()
    await dispose_db()


app = FastAPI(title="FinChat AI Service", version="0.1.0", lifespan=lifespan)


def get_ai_repository() -> AIRepository:
    return AIRepository()


# ---------------------------------------------------------------------------
# Telemetry persistence helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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
    request_start = time.perf_counter()

    # ── Guardrail 1: message length ──────────────────────────────────────────
    if len(payload.message) > _MAX_MESSAGE_LENGTH:
        logger.warning(
            "GUARDRAIL:message_too_long user_id=%s session_id=%s length=%d limit=%d",
            payload.user_id, payload.session_id, len(payload.message), _MAX_MESSAGE_LENGTH,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Message exceeds the {_MAX_MESSAGE_LENGTH}-character limit.",
        )

    logger.info(
        "REQUEST:start user_id=%s role=%s session_id=%s msg_length=%d",
        payload.user_id, payload.role, payload.session_id, len(payload.message),
    )

    run = await repo.create_run(
        session_id=payload.session_id,
        user_id=payload.user_id,
    )
    tool_telemetry: list[ToolCallTelemetry] = []
    publisher = StreamEventPublisher(session_id=payload.session_id)

    try:
        # ── PII scan ─────────────────────────────────────────────────────────
        await publisher.publish_status("pii_scan", "Scanning message for sensitive data (PII)...")
        redaction = redact_pii(payload.message)
        pii_mapping: dict[str, str] = {}
        if redaction.has_pii:
            for entity in redaction.entities:
                placeholder = DEFAULT_REPLACEMENTS.get(entity.entity_type, "<REDACTED>")
                pii_mapping[placeholder] = entity.text

            entity_types = [e.entity_type for e in redaction.entities]
            logger.info(
                "PII:redacted user_id=%s session_id=%s entities=%s",
                payload.user_id, payload.session_id, entity_types,
            )
            await publisher.publish_status(
                "pii_redacted",
                f"Sensitive data ({len(redaction.entities)} entities) redacted for privacy.",
            )
            await repo.log_trace(
                run_id=run.id,
                agent_name="pii_redactor",
                input_state={"has_pii": True, "entity_count": len(redaction.entities)},
                output_state={"masked_entities": entity_types},
            )

        # ── Tool resolution ───────────────────────────────────────────────────
        tools = await get_all_partitioned_mcp_tools(
            user_id=payload.user_id,
            role=payload.role,
            telemetry_records=tool_telemetry,
            publisher=publisher,
            pii_mapping=pii_mapping,
        )
        total_tools = sum(len(v) for v in tools.values())
        logger.info(
            "TOOLS:resolved user_id=%s session_id=%s total_tools=%d domains=%s",
            payload.user_id, payload.session_id, total_tools,
            {k: len(v) for k, v in tools.items()},
        )

        # ── Guardrail 2: wall-clock timeout on the full coordinator run ───────
        try:
            result = await asyncio.wait_for(
                run_coordinator(
                    message=redaction.redacted_text,
                    user_id=payload.user_id,
                    role=payload.role,
                    session_id=payload.session_id,
                    account_number=payload.account_number,
                    tools=tools,
                    checkpointer=get_checkpointer(),
                    publisher=publisher,
                ),
                timeout=_REQUEST_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            elapsed = int((time.perf_counter() - request_start) * 1000)
            logger.error(
                "GUARDRAIL:timeout run_id=%s user_id=%s session_id=%s elapsed_ms=%d limit_sec=%d",
                run.id, payload.user_id, payload.session_id, elapsed, _REQUEST_TIMEOUT_SEC,
            )
            await publisher.publish_error(
                "The request took too long to process. Please try a simpler query."
            )
            await repo.complete_run(run.id, status=RunStatus.FAILED,
                                    error_message="request_timeout")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="AI processing timed out. Please try again.",
            )

        elapsed_ms = int((time.perf_counter() - request_start) * 1000)
        total_tokens = sum(
            c.prompt_tokens + c.completion_tokens for c in result.llm_calls
        )
        logger.info(
            "REQUEST:complete run_id=%s user_id=%s session_id=%s intent=%s "
            "confidence=%.2f tools_called=%s elapsed_ms=%d total_tokens=%d",
            run.id, payload.user_id, payload.session_id,
            result.intent, result.confidence, result.tools_called,
            elapsed_ms, total_tokens,
        )

        # ── Guardrail 3: low-confidence warning (logged, not blocked) ─────────
        if result.intent == "unknown" or result.confidence < 0.4:
            logger.warning(
                "GUARDRAIL:low_confidence run_id=%s user_id=%s intent=%s confidence=%.2f reason=%s",
                run.id, payload.user_id, result.intent, result.confidence, result.reason,
            )

        await _persist_run_telemetry(
            repo, run_id=run.id, result=result, tool_telemetry=tool_telemetry,
        )
        await repo.complete_run(run.id, status=RunStatus.COMPLETED, intent=result.intent)
        await publisher.publish_done(
            reply=result.reply,
            tools_called=result.tools_called,
            intent=result.intent,
        )

    except HTTPException:
        raise  # Already handled above, re-raise as-is

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - request_start) * 1000)
        logger.exception(
            "REQUEST:failed run_id=%s user_id=%s session_id=%s elapsed_ms=%d error=%s",
            run.id, payload.user_id, payload.session_id, elapsed_ms, exc,
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
                logger.warning(
                    "Failed to persist partial tool telemetry for run_id=%s", run.id
                )
        try:
            await repo.complete_run(
                run.id, status=RunStatus.FAILED, error_message=str(exc),
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
