from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid

from sqlalchemy import JSON, Column, DateTime, Text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: int = Field(index=True)
    user_id: int = Field(index=True)
    intent: str | None = Field(default=None, max_length=64, index=True)
    started_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    finished_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    status: str = Field(default=RunStatus.RUNNING.value, max_length=32, index=True)
    error_message: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )


class LLMCall(SQLModel, table=True):
    __tablename__ = "llm_calls"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="agent_runs.id", index=True)
    node_name: str = Field(max_length=100, index=True)
    model_name: str = Field(max_length=100)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ToolCall(SQLModel, table=True):
    __tablename__ = "tool_calls"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="agent_runs.id", index=True)
    tool_name: str = Field(max_length=100, index=True)
    mcp_server: str = Field(max_length=100, index=True)
    input_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    output_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    latency_ms: int = Field(default=0, ge=0)
    success: bool = Field(default=True)
    error_message: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AgentTrace(SQLModel, table=True):
    __tablename__ = "agent_traces"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="agent_runs.id", index=True)
    agent_name: str = Field(max_length=100, index=True)
    input_state: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    output_state: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

