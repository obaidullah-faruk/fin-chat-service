import warnings
warnings.filterwarnings("ignore")

import logging
import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools.account_tools import get_account_info, get_balance


class SuppressSSEClosedResourceFilter(logging.Filter):
    """Suppress harmless AnyIO ClosedResourceError logged during normal SSE session teardown."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "Error in standalone SSE writer" in msg or "ClosedResourceError" in msg:
            return False
        return True


logging.getLogger("mcp.server.streamable_http").addFilter(SuppressSSEClosedResourceFilter())

mcp = FastMCP("accounts-mcp")
mcp.tool()(get_balance)
mcp.tool()(get_account_info)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "accounts-mcp"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8002"))
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        path="/mcp",
    )
