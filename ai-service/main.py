from fastapi import Depends, FastAPI

from schemas.chat import ChatRequest, ChatResponse
from security.auth import verify_internal_caller

app = FastAPI(title="FinChat AI Service", version="0.1.0")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/chat/process",
    response_model=ChatResponse,
    dependencies=[Depends(verify_internal_caller)],
)
async def process_chat(payload: ChatRequest) -> ChatResponse:
    return ChatResponse(
        reply=f'[AI Service Echo] Received: "{payload.message}"',
        tools_called=[],
    )

