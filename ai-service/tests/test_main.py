from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_process_chat_requires_valid_internal_key(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    payload = {
        "user_id": 1,
        "role": "customer",
        "account_number": "FC1000000001",
        "session_id": 10,
        "message": "What is my balance?",
    }

    missing_key_resp = client.post("/chat/process", json=payload)
    assert missing_key_resp.status_code == 403

    wrong_key_resp = client.post(
        "/chat/process",
        json=payload,
        headers={"X-Internal-Key": "wrong-key"},
    )
    assert wrong_key_resp.status_code == 403


def test_process_chat_echoes_message(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    payload = {
        "user_id": 1,
        "role": "customer",
        "account_number": "FC1000000001",
        "session_id": 10,
        "message": "What is my balance?",
    }

    response = client.post(
        "/chat/process",
        json=payload,
        headers={"X-Internal-Key": "test-internal-key"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "reply": '[AI Service Echo] Received: "What is my balance?"',
        "tools_called": [],
    }

