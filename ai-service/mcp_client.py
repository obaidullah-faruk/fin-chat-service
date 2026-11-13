import asyncio
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
import json
import time
from typing import Any

try:
    from fastmcp import Client
    from langchain_core.tools import BaseTool, StructuredTool
    from langchain_mcp_adapters.client import MultiServerMCPClient
except ImportError:
    Client = Any  # type: ignore[assignment,misc]
    BaseTool = Any  # type: ignore[assignment,misc]
    StructuredTool = Any  # type: ignore[assignment,misc]
    MultiServerMCPClient = Any  # type: ignore[assignment,misc]
from pydantic import BaseModel

from config import get_settings
from security.authorization import (
    ToolAuthorizationError,
    check_tool_authorization,
    is_tool_allowed,
)


def get_mcp_server_urls() -> dict[str, str]:
    return get_settings().mcp_server_urls


def build_mcp_connections(
    server_urls: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    urls = server_urls if server_urls is not None else get_mcp_server_urls()
    return {
        server_name: {
            "url": url,
            "transport": "streamable_http",
        }
        for server_name, url in urls.items()
    }


@dataclass(slots=True)
class DiscoveredMCPTool:
    server_name: str
    tool: BaseTool


@dataclass(slots=True)
class ToolCallTelemetry:
    tool_name: str
    mcp_server: str
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    latency_ms: int
    success: bool
    error_message: str | None = None


_cache_lock = asyncio.Lock()
_cached_tools: list[DiscoveredMCPTool] | None = None


def clear_mcp_tool_cache() -> None:
    """Reset the in-memory discovered MCP tool cache."""
    global _cached_tools
    _cached_tools = None


def _strip_user_id_from_schema(
    args_schema: dict[str, Any] | type[BaseModel] | None,
) -> dict[str, Any]:
    if args_schema is None:
        return {"type": "object", "properties": {}, "required": []}

    if isinstance(args_schema, type) and issubclass(args_schema, BaseModel):
        schema = deepcopy(args_schema.model_json_schema())
    elif isinstance(args_schema, dict):
        schema = deepcopy(args_schema)
    else:
        return {"type": "object", "properties": {}, "required": []}

    properties = schema.get("properties")
    if isinstance(properties, dict):
        properties.pop("user_id", None)
    else:
        schema["properties"] = {}

    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [field for field in required if field != "user_id"]
    else:
        schema["required"] = []

    schema.setdefault("type", "object")
    return schema


def _normalize_tool_output(raw_result: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(raw_result, tuple) and len(raw_result) == 2:
        raw_result = raw_result[0]

    if isinstance(raw_result, dict):
        return json.dumps(raw_result), raw_result

    if isinstance(raw_result, list):
        text_parts: list[str] = []
        for item in raw_result:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
            elif hasattr(item, "text") and isinstance(item.text, str):
                text_parts.append(item.text)
            else:
                text_parts.append(str(item))
        combined = "\n".join(part for part in text_parts if part)
        return _parse_text_and_dict(combined)

    if isinstance(raw_result, str):
        return _parse_text_and_dict(raw_result)

    serialized = str(raw_result)
    return serialized, {"result": serialized}


def _parse_text_and_dict(text: str) -> tuple[str, dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return "", {}
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return stripped, parsed
        return stripped, {"result": parsed}
    except json.JSONDecodeError:
        return text, {"text": text}


async def discover_mcp_tools(
    client: MultiServerMCPClient | None = None,
    server_urls: dict[str, str] | None = None,
) -> list[DiscoveredMCPTool]:
    """Discover tools from all configured MCP servers, preserving server ownership."""
    connections = build_mcp_connections(server_urls)
    mcp_client = client or MultiServerMCPClient(
        connections,
        handle_tool_errors=False,
    )

    server_names = list(connections.keys())
    per_server_tools = await asyncio.gather(
        *(mcp_client.get_tools(server_name=name) for name in server_names)
    )

    discovered: list[DiscoveredMCPTool] = []
    for server_name, tools in zip(server_names, per_server_tools, strict=True):
        for tool in tools:
            discovered.append(DiscoveredMCPTool(server_name=server_name, tool=tool))
    return discovered


async def get_discovered_mcp_tools(
    *,
    force_refresh: bool = False,
) -> list[DiscoveredMCPTool]:
    """Return cached MCP tools, discovering them on first access."""
    global _cached_tools
    if _cached_tools is not None and not force_refresh:
        return _cached_tools

    async with _cache_lock:
        if _cached_tools is None or force_refresh:
            discovered = await discover_mcp_tools()
            if discovered:
                _cached_tools = discovered
            return discovered
        return _cached_tools


def bind_mcp_tools_for_user(
    discovered_tools: list[DiscoveredMCPTool],
    *,
    user_id: int,
    role: str | None = None,
    telemetry_records: list[ToolCallTelemetry] | None = None,
) -> list[StructuredTool]:
    """Wrap discovered MCP tools to inject verified user_id, check role authorization, and record telemetry."""
    bound_tools: list[StructuredTool] = []

    for entry in discovered_tools:
        server_name = entry.server_name
        base_tool = entry.tool
        exposed_schema = _strip_user_id_from_schema(base_tool.args_schema)

        async def _invoke_bound_tool(
            _base_tool: BaseTool = base_tool,
            _server_name: str = server_name,
            **kwargs: Any,
        ) -> str:
            call_args = {**kwargs, "user_id": user_id}
            started = time.perf_counter()

            # Defense-in-depth: Agent-level authorization check before tool invocation
            if role is not None:
                try:
                    check_tool_authorization(role, _base_tool.name)
                except Exception as auth_exc:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    if telemetry_records is not None:
                        telemetry_records.append(
                            ToolCallTelemetry(
                                tool_name=_base_tool.name,
                                mcp_server=_server_name,
                                input_json=call_args,
                                output_json={},
                                latency_ms=latency_ms,
                                success=False,
                                error_message=str(auth_exc),
                            )
                        )
                    raise

            try:
                raw_result = await _base_tool.ainvoke(call_args)
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                if telemetry_records is not None:
                    telemetry_records.append(
                        ToolCallTelemetry(
                            tool_name=_base_tool.name,
                            mcp_server=_server_name,
                            input_json=call_args,
                            output_json={},
                            latency_ms=latency_ms,
                            success=False,
                            error_message=str(exc),
                        )
                    )
                raise

            latency_ms = int((time.perf_counter() - started) * 1000)
            llm_text, output_dict = _normalize_tool_output(raw_result)
            if telemetry_records is not None:
                telemetry_records.append(
                    ToolCallTelemetry(
                        tool_name=_base_tool.name,
                        mcp_server=_server_name,
                        input_json=call_args,
                        output_json=output_dict,
                        latency_ms=latency_ms,
                        success=True,
                    )
                )
            return llm_text

        bound_tools.append(
            StructuredTool.from_function(
                coroutine=_invoke_bound_tool,
                name=base_tool.name,
                description=base_tool.description or base_tool.name,
                args_schema=exposed_schema,
            )
        )

    return bound_tools


async def get_user_mcp_tools(
    *,
    user_id: int,
    role: str | None = None,
    telemetry_records: list[ToolCallTelemetry] | None = None,
    discovered_tools: list[DiscoveredMCPTool] | None = None,
) -> list[StructuredTool]:
    """Get request-scoped MCP tools bound to verified user_id and checked against role."""
    tools_to_bind = (
        discovered_tools
        if discovered_tools is not None
        else await get_discovered_mcp_tools()
    )
    return bind_mcp_tools_for_user(
        tools_to_bind,
        user_id=user_id,
        role=role,
        telemetry_records=telemetry_records,
    )


def partition_mcp_tools_by_domain(
    discovered_tools: Sequence[DiscoveredMCPTool],
) -> dict[str, list[DiscoveredMCPTool]]:
    """Group discovered MCP tools by their parent server domain name."""
    partitioned: dict[str, list[DiscoveredMCPTool]] = {
        "accounts": [],
        "transactions": [],
        "service": [],
    }
    for item in discovered_tools:
        partitioned.setdefault(item.server_name, []).append(item)
    return partitioned


async def get_domain_mcp_tools(
    domain: str,
    *,
    user_id: int,
    role: str | None = None,
    telemetry_records: list[ToolCallTelemetry] | None = None,
    discovered_tools: list[DiscoveredMCPTool] | None = None,
) -> list[StructuredTool]:
    """Get MCP tools for a specific domain/server, bound to user_id and checked against role."""
    all_tools = (
        discovered_tools
        if discovered_tools is not None
        else await get_discovered_mcp_tools()
    )
    domain_tools = [t for t in all_tools if t.server_name == domain]
    return bind_mcp_tools_for_user(
        domain_tools,
        user_id=user_id,
        role=role,
        telemetry_records=telemetry_records,
    )


async def get_accounts_tools(
    *,
    user_id: int,
    role: str | None = None,
    telemetry_records: list[ToolCallTelemetry] | None = None,
    discovered_tools: list[DiscoveredMCPTool] | None = None,
) -> list[StructuredTool]:
    """Get tools scoped for Accounts Agent (get_balance, get_account_info)."""
    return await get_domain_mcp_tools(
        "accounts",
        user_id=user_id,
        role=role,
        telemetry_records=telemetry_records,
        discovered_tools=discovered_tools,
    )


async def get_transactions_tools(
    *,
    user_id: int,
    role: str | None = None,
    telemetry_records: list[ToolCallTelemetry] | None = None,
    discovered_tools: list[DiscoveredMCPTool] | None = None,
) -> list[StructuredTool]:
    """Get tools scoped for Transaction Agent (get_transactions, get_statement)."""
    return await get_domain_mcp_tools(
        "transactions",
        user_id=user_id,
        role=role,
        telemetry_records=telemetry_records,
        discovered_tools=discovered_tools,
    )


async def get_service_tools(
    *,
    user_id: int,
    role: str | None = None,
    telemetry_records: list[ToolCallTelemetry] | None = None,
    discovered_tools: list[DiscoveredMCPTool] | None = None,
) -> list[StructuredTool]:
    """Get tools scoped for Service Agent (request_cheque_book, update_address, get_kyc_status)."""
    return await get_domain_mcp_tools(
        "service",
        user_id=user_id,
        role=role,
        telemetry_records=telemetry_records,
        discovered_tools=discovered_tools,
    )


async def get_all_partitioned_mcp_tools(
    *,
    user_id: int,
    role: str | None = None,
    telemetry_records: list[ToolCallTelemetry] | None = None,
    discovered_tools: list[DiscoveredMCPTool] | None = None,
) -> dict[str, list[StructuredTool]]:
    """Return a dictionary of domain -> list of bound tools for all sub-agents."""
    all_discovered = (
        discovered_tools
        if discovered_tools is not None
        else await get_discovered_mcp_tools()
    )
    partitioned = partition_mcp_tools_by_domain(all_discovered)
    return {
        domain: bind_mcp_tools_for_user(
            tools,
            user_id=user_id,
            role=role,
            telemetry_records=telemetry_records,
        )
        for domain, tools in partitioned.items()
    }


def _extract_tool_payload(result: Any) -> dict[str, Any]:
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data

    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
                return {"result": parsed}
            except json.JSONDecodeError:
                return {"text": text}

    return {}


async def call_mcp_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    urls = get_mcp_server_urls()
    server_url = urls.get(server_name)
    if not server_url:
        raise ValueError(f"Unknown MCP server: {server_name}")

    async with Client(server_url) as client:
        result = await client.call_tool(tool_name, arguments)

    if getattr(result, "is_error", False):
        raise RuntimeError(f"MCP tool '{tool_name}' returned an error: {result.content}")

    return _extract_tool_payload(result)
