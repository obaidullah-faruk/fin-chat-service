import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.checkpointer import (
    close_checkpointer,
    get_checkpointer,
    init_checkpointer,
    set_checkpointer,
)


@pytest.fixture(autouse=True)
def clean_checkpointer_state():
    yield
    set_checkpointer(None)


def test_get_and_set_checkpointer():
    default_saver = get_checkpointer()
    assert default_saver is not None

    custom_saver = MagicMock()
    set_checkpointer(custom_saver)
    assert get_checkpointer() is custom_saver

    set_checkpointer(None)
    new_default = get_checkpointer()
    assert new_default is not None
    assert new_default is not custom_saver


def test_init_checkpointer_falls_back_when_redis_unreachable():
    # If connection to Redis fails, it falls back to MemorySaver without crashing
    mock_redis_cls = MagicMock()
    mock_redis_cls.from_conn_string.side_effect = ConnectionError("Redis connection refused")

    with patch("db.checkpointer.HAS_REDIS_SAVER", True), patch(
        "db.checkpointer.AsyncRedisSaver", mock_redis_cls
    ):
        saver = asyncio.run(init_checkpointer("redis://nonexistent:6379/0"))
        assert saver is not None
        assert get_checkpointer() is saver


def test_close_checkpointer_cleans_up():
    mock_saver = MagicMock()
    mock_saver.aclose = AsyncMock()
    set_checkpointer(mock_saver)

    asyncio.run(close_checkpointer())
    mock_saver.aclose.assert_awaited_once()
    assert get_checkpointer() is not mock_saver


def test_thread_id_isolated_per_session():
    # Verify two different sessions maintain separate checkpoints
    saver = get_checkpointer()
    cfg1 = {"configurable": {"thread_id": "session_1"}}
    cfg2 = {"configurable": {"thread_id": "session_2"}}

    saver.put(cfg1, {"messages": ["hello session 1"]}, {})
    saver.put(cfg2, {"messages": ["hello session 2"]}, {})

    state1 = saver.get_tuple(cfg1)
    state2 = saver.get_tuple(cfg2)

    assert state1 is not None
    assert state2 is not None
    # Verify state isolation
    assert state1[0]["messages"] == ["hello session 1"]
    assert state2[0]["messages"] == ["hello session 2"]
