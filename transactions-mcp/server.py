import warnings
warnings.filterwarnings("ignore")

import logging
import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools.transaction_tools import get_statement, get_transactions


class SuppressSSEClosedResourceFilter(logging.Filter):
    """Suppress harmless AnyIO ClosedResourceError logged during normal SSE session teardown."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "Error in standalone SSE writer" in msg or "ClosedResourceError" in msg:
            return False
        return True


logging.getLogger("mcp.server.streamable_http").addFilter(SuppressSSEClosedResourceFilter())

mcp = FastMCP("transactions-mcp")
mcp.tool()(get_transactions)
mcp.tool()(get_statement)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "transactions-mcp"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8003"))
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        path="/mcp",
    )
