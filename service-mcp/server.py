import warnings
warnings.filterwarnings("ignore")

import logging
import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools.service_tools import (
    get_kyc_status,
    get_pending_reviews,
    lookup_customer,
    request_cheque_book,
    update_address,
)


class SuppressSSEClosedResourceFilter(logging.Filter):
    """Suppress harmless AnyIO ClosedResourceError logged during normal SSE session teardown."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "Error in standalone SSE writer" in msg or "ClosedResourceError" in msg:
            return False
        return True


logging.getLogger("mcp.server.streamable_http").addFilter(SuppressSSEClosedResourceFilter())

mcp = FastMCP("service-mcp")
mcp.tool()(request_cheque_book)
mcp.tool()(update_address)
mcp.tool()(get_kyc_status)
mcp.tool()(lookup_customer)
mcp.tool()(get_pending_reviews)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "service-mcp"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8004"))
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        path="/mcp",
    )
