import os

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from tools.service_tools import get_kyc_status, request_cheque_book, update_address

mcp = FastMCP("service-mcp")
mcp.tool()(request_cheque_book)
mcp.tool()(update_address)
mcp.tool()(get_kyc_status)


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
