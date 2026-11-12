import pytest

from config import get_settings


def test_settings_defaults(monkeypatch):
    for var in (
        "INTERNAL_API_KEY",
        "DJANGO_API_URL",
        "REDIS_URL",
        "AI_DB_URL",
        "ACCOUNTS_MCP_URL",
        "TRANSACTIONS_MCP_URL",
        "SERVICE_MCP_URL",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "GEMINI_TEMPERATURE",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = get_settings()
    assert settings.django_api_url == "http://backend:8000"
    assert settings.redis_url == "redis://redis:6379/0"
    assert settings.gemini_model == "gemini-2.0-flash"
    assert settings.gemini_temperature == 0.0
    assert settings.mcp_server_urls == {
        "accounts": "http://accounts-mcp:8002/mcp",
        "transactions": "http://transactions-mcp:8003/mcp",
        "service": "http://service-mcp:8004/mcp",
    }


def test_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "secret-123")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_TEMPERATURE", "0.2")
    monkeypatch.setenv("ACCOUNTS_MCP_URL", "http://localhost:8002/mcp")

    settings = get_settings()
    assert settings.internal_api_key == "secret-123"
    assert settings.require_gemini_api_key() == "AIza-test-key"
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.gemini_temperature == 0.2
    assert settings.mcp_server_urls["accounts"] == "http://localhost:8002/mcp"


@pytest.mark.parametrize("bad_value", ["", "   ", "Create_key", "your-gemini-api-key"])
def test_require_gemini_api_key_rejects_missing_or_placeholder(monkeypatch, bad_value):
    monkeypatch.setenv("GEMINI_API_KEY", bad_value)
    settings = get_settings()

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not configured"):
        settings.require_gemini_api_key()

