from typing import Literal
from pydantic import BaseModel, Field


class ChatMessageItem(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    user_id: int
    role: str = Field(min_length=1, max_length=50)
    account_number: str | None = None
    session_id: int
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessageItem] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    tools_called: list[str] = Field(default_factory=list)
    intent: str | None = None
