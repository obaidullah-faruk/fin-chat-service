import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
import httpx

try:
    from redis.asyncio import Redis, from_url as redis_from_url
    HAS_REDIS = True
except ImportError:
    Redis = None  # type: ignore[assignment,misc]
    redis_from_url = None  # type: ignore[assignment,misc]
    HAS_REDIS = False

try:
    from rest_framework_simplejwt.tokens import AccessToken
    HAS_SIMPLE_JWT = True
except ImportError:
    AccessToken = None  # type: ignore[assignment,misc]
    HAS_SIMPLE_JWT = False

from .models import ChatMessage, ChatSession

logger = logging.getLogger("finchat.chat.websocket")

WS_PATH_REGEX = re.compile(r"^/ws/chat/(?P<session_id>\d+)/?$")


def _get_user_for_token(token_str: str) -> Any:
    """Validate JWT access token and return the User instance."""
    if not HAS_SIMPLE_JWT or AccessToken is None:
        raise ValueError("JWT authentication library not available.")

    access_token = AccessToken(token_str)
    user_id = access_token.get("user_id")
    if not user_id:
        raise ValueError("Token missing user_id.")

    User = get_user_model()
    try:
        user = User.objects.select_related("role", "bank_account").get(id=user_id, is_active=True)
        return user
    except User.DoesNotExist as exc:
        raise ValueError("User not found or inactive.") from exc


def _get_session_for_user(session_id: int, user: Any) -> ChatSession:
    """Ensure the chat session exists and belongs to the given user."""
    return ChatSession.objects.get(id=session_id, user=user)


def _save_user_message(session: ChatSession, content: str) -> ChatMessage:
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.USER,
        content=content,
    )
    if not session.title:
        session.title = content[:60]
        session.save(update_fields=["title", "updated_at"])
    return msg


def _save_assistant_message(
    session: ChatSession,
    reply: str,
    tools_called: list[str] | None = None,
) -> ChatMessage:
    return ChatMessage.objects.create(
        session=session,
        role=ChatMessage.Role.ASSISTANT,
        content=reply,
        metadata={"mode": "ai_service_websocket", "tools_called": tools_called or []},
    )


def _get_session_history(session: ChatSession, limit: int = 10) -> list[dict[str, str]]:
    recent = list(session.messages.order_by("-created_at", "-id")[:limit])
    recent.reverse()
    return [{"role": m.role, "content": m.content} for m in recent]


async def _trigger_ai_service(user: Any, session: ChatSession, message: str) -> None:
    """Call AI service asynchronously on behalf of the WebSocket client."""
    account = getattr(user, "bank_account", None)
    history = await sync_to_async(_get_session_history)(session)
    payload = {
        "user_id": user.id,
        "role": user.role.name,
        "account_number": account.account_number if account else None,
        "session_id": session.id,
        "message": message,
        "history": history,
    }
    headers = {"X-Internal-Key": getattr(settings, "INTERNAL_API_KEY", "")}
    ai_service_url = getattr(settings, "AI_SERVICE_URL", "http://ai-service:8001").rstrip("/")
    url = f"{ai_service_url}/chat/process"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("reply", "")
            tools_called = data.get("tools_called", [])
            await sync_to_async(_save_assistant_message)(session, reply, tools_called)
    except Exception as exc:
        logger.error(
            "WebSocket AI service invocation failed for session %s: %s",
            session.id,
            exc,
        )
        if HAS_REDIS and redis_from_url:
            try:
                redis_client = redis_from_url(
                    getattr(settings, "REDIS_URL", "redis://redis:6379/0"),
                    decode_responses=True,
                )
                await redis_client.publish(
                    f"stream:{session.id}",
                    json.dumps(
                        {
                            "type": "error",
                            "error": "AI service is temporarily unavailable.",
                        }
                    ),
                )
                await redis_client.aclose()
            except Exception:
                pass


async def _redis_pubsub_listener(
    session_id: int,
    send: Any,
    stop_event: asyncio.Event,
) -> None:
    """Listen to Redis Pub/Sub channel and forward all streaming events to WebSocket."""
    if not HAS_REDIS or redis_from_url is None:
        logger.warning("Redis is not available; streaming listener cannot start.")
        return

    redis_url = getattr(settings, "REDIS_URL", "redis://redis:6379/0")
    client = None
    pubsub = None

    try:
        client = redis_from_url(redis_url, decode_responses=True)
        pubsub = client.pubsub()
        channel_name = f"stream:{session_id}"
        await pubsub.subscribe(channel_name)
        logger.info("Subscribed to Redis channel %s for WebSocket", channel_name)

        while not stop_event.is_set():
            try:
                msg = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=1.5,
                )
            except asyncio.TimeoutError:
                continue

            if msg is not None and msg.get("type") == "message":
                data = msg.get("data")
                if isinstance(data, (str, bytes)):
                    text = data if isinstance(data, str) else data.decode("utf-8")
                    await send({"type": "websocket.send", "text": text})

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("Error in Redis Pub/Sub listener for session %s: %s", session_id, exc)
    finally:
        if pubsub is not None:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass


async def chat_websocket_application(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """Pure ASGI 3.0 WebSocket handler for FinChat streaming."""
    path = scope.get("path", "")
    match = WS_PATH_REGEX.match(path)
    if not match:
        logger.warning("WebSocket rejected: invalid path '%s'", path)
        await send({"type": "websocket.close", "code": 4004})
        return

    session_id = int(match.group("session_id"))

    # Extract JWT token from query string
    query_str = scope.get("query_string", b"").decode("utf-8")
    query_params = parse_qs(query_str)
    tokens = query_params.get("token", [])
    if not tokens:
        logger.warning("WebSocket rejected: missing 'token' query parameter")
        await send({"type": "websocket.close", "code": 4001})
        return

    raw_token = tokens[0]

    # Authenticate user
    try:
        user = await sync_to_async(_get_user_for_token)(raw_token)
    except Exception as exc:
        logger.warning("WebSocket authentication failed: %s", exc)
        await send({"type": "websocket.close", "code": 4001})
        return

    # Verify session ownership
    try:
        session = await sync_to_async(_get_session_for_user)(session_id, user)
    except Exception as exc:
        logger.warning(
            "WebSocket session verification failed: user_id=%s session_id=%s error=%s",
            user.id,
            session_id,
            exc,
        )
        await send({"type": "websocket.close", "code": 4004})
        return

    # Accept connection
    await send({"type": "websocket.accept"})
    logger.info("WebSocket connected: user_id=%s session_id=%s", user.id, session_id)

    stop_event = asyncio.Event()
    redis_task = asyncio.create_task(
        _redis_pubsub_listener(session_id, send, stop_event)
    )

    try:
        while True:
            event = await receive()
            event_type = event.get("type")

            if event_type == "websocket.disconnect":
                logger.info("WebSocket disconnected: session_id=%s", session_id)
                break

            if event_type == "websocket.receive":
                text_data = event.get("text")
                if not text_data:
                    continue

                try:
                    payload = json.loads(text_data)
                except json.JSONDecodeError:
                    continue

                content = payload.get("content", "").strip()
                if not content:
                    continue

                # Check if session is closed
                session_status = await sync_to_async(lambda: session.status)()
                if session_status == ChatSession.Status.CLOSED:
                    await send({
                        "type": "websocket.send",
                        "text": json.dumps({
                            "type": "error",
                            "error": "This chat session is closed. No new messages can be added.",
                        }),
                    })
                    continue

                # Persist user message and trigger AI service
                await sync_to_async(_save_user_message)(session, content)
                asyncio.create_task(_trigger_ai_service(user, session, content))

    finally:
        stop_event.set()
        redis_task.cancel()
        try:
            await redis_task
        except asyncio.CancelledError:
            pass

