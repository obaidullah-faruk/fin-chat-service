from pydantic import BaseModel, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    class BaseSettings(BaseModel):  # type: ignore[no-redef]
        def __init__(self, **data):
            super().__init__(**data)

    def SettingsConfigDict(**kwargs):  # type: ignore[misc]
        return kwargs

_PLACEHOLDER_GEMINI_KEYS = {"", "create_key", "your-gemini-api-key"}


class Settings(BaseSettings):
    """Runtime configuration for the FinChat AI orchestration service."""

    model_config = SettingsConfigDict(
        extra="ignore",
    )

    internal_api_key: str = Field(default="")
    django_api_url: str = Field(default="http://backend:8000")
    redis_url: str = Field(default="redis://redis:6379/0")
    ai_db_url: str = Field(
        default="postgresql+asyncpg://finchat_ai:finchat_ai_secret@ai-db:5432/finchat_ai"
    )

    accounts_mcp_url: str = Field(default="http://accounts-mcp:8002/mcp")
    transactions_mcp_url: str = Field(default="http://transactions-mcp:8003/mcp")
    service_mcp_url: str = Field(default="http://service-mcp:8004/mcp")

    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3.8-flash")
    gemini_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @property
    def mcp_server_urls(self) -> dict[str, str]:
        return {
            "accounts": self.accounts_mcp_url,
            "transactions": self.transactions_mcp_url,
            "service": self.service_mcp_url,
        }

    def require_gemini_api_key(self) -> str:
        key = self.gemini_api_key.strip()
        if key.lower() in _PLACEHOLDER_GEMINI_KEYS:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Set a valid key in .env."
            )
        return key


def get_settings() -> Settings:
    """Load current settings from environment variables."""
    return Settings()
