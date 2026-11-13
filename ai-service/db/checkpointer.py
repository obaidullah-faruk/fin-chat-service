from contextlib import AbstractAsyncContextManager
import logging
from typing import Any

from config import get_settings

logger = logging.getLogger("finchat.checkpointer")

try:
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver
    HAS_REDIS_SAVER = True
except ImportError:
    AsyncRedisSaver = None  # type: ignore[assignment,misc]
    HAS_REDIS_SAVER = False

try:
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    class MemorySaver:  # type: ignore[no-redef]
        """In-memory checkpoint saver stub when langgraph is not installed."""

        def __init__(self) -> None:
            self.storage: dict[str, Any] = {}

        def get_tuple(self, config: dict[str, Any]) -> Any:
            thread_id = config.get("configurable", {}).get("thread_id")
            return self.storage.get(thread_id)

        def put(
            self,
            config: dict[str, Any],
            checkpoint: Any,
            metadata: Any,
            new_versions: Any = None,
        ) -> dict[str, Any]:
            thread_id = config.get("configurable", {}).get("thread_id")
            self.storage[thread_id] = (checkpoint, metadata)
            return config


_active_checkpointer: Any = None
_checkpointer_context: Any = None


async def init_checkpointer(redis_url: str | None = None) -> Any:
    """
    Initialize checkpointer persistence.
    Attempts to connect to Redis using AsyncRedisSaver.
    Falls back gracefully to MemorySaver for testing or offline environments.
    """
    global _active_checkpointer, _checkpointer_context
    url = redis_url or get_settings().redis_url

    if HAS_REDIS_SAVER and url:
        try:
            logger.info("Initializing Redis checkpointer at: %s", url)
            saver_cm = AsyncRedisSaver.from_conn_string(url)
            # Handle AsyncRedisSaver as context manager if required by version
            if hasattr(saver_cm, "__aenter__"):
                _checkpointer_context = saver_cm
                _active_checkpointer = await saver_cm.__aenter__()
            else:
                _active_checkpointer = saver_cm

            if hasattr(_active_checkpointer, "asetup"):
                await _active_checkpointer.asetup()

            logger.info("Redis checkpointer connected and initialized.")
            return _active_checkpointer
        except Exception as exc:
            logger.warning(
                "Redis connection to %s failed (%s). Falling back to MemorySaver.",
                url,
                exc,
            )

    logger.info("Using in-memory checkpoint saver (MemorySaver).")
    _active_checkpointer = MemorySaver()
    return _active_checkpointer


def get_checkpointer() -> Any:
    """Return the currently active checkpointer or an in-memory fallback."""
    global _active_checkpointer
    if _active_checkpointer is None:
        _active_checkpointer = MemorySaver()
    return _active_checkpointer


def set_checkpointer(checkpointer: Any) -> None:
    """Manually assign or override the checkpointer (useful for unit testing)."""
    global _active_checkpointer
    _active_checkpointer = checkpointer


async def close_checkpointer() -> None:
    """Gracefully terminate checkpointer connections on shutdown."""
    global _active_checkpointer, _checkpointer_context
    if _checkpointer_context is not None and hasattr(_checkpointer_context, "__aexit__"):
        try:
            await _checkpointer_context.__aexit__(None, None, None)
        except Exception as exc:
            logger.warning("Error exiting Redis checkpointer context: %s", exc)
        _checkpointer_context = None

    if _active_checkpointer is not None and hasattr(_active_checkpointer, "aclose"):
        try:
            await _active_checkpointer.aclose()
        except Exception as exc:
            logger.warning("Error closing checkpointer: %s", exc)

    _active_checkpointer = None

