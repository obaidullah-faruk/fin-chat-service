from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: int
    role: str = Field(min_length=1, max_length=50)
    account_number: str | None = None
    session_id: int
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    tools_called: list[str] = Field(default_factory=list)

