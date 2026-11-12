import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Service MCP Service", version="0.1.0")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "service-mcp"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)

