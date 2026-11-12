import json
import os
from typing import Any

from fastmcp import Client


def get_mcp_server_urls() -> dict[str, str]:
    return {
        "accounts": os.environ.get("ACCOUNTS_MCP_URL", "http://accounts-mcp:8002/mcp"),
        "transactions": os.environ.get("TRANSACTIONS_MCP_URL", "http://transactions-mcp:8003/mcp"),
        "service": os.environ.get("SERVICE_MCP_URL", "http://service-mcp:8004/mcp"),
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

