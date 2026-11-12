import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Transactions MCP Service", version="0.1.0")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "transactions-mcp"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)

