import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from streaming import StreamEventPublisher


class MockRedisPubSub:
    """In-memory mock of Redis Pub/Sub for multi-instance auto-scaling simulation."""

    def __init__(self):
        self._channels: dict[str, list[asyncio.Queue]] = {}

    async def publish(self, channel: str, message: str) -> int:
        queues = self._channels.get(channel, [])
        for q in queues:
            await q.put(message)
        return len(queues)

    def subscribe(self, channel: str) -> "MockSubscriber":
        q: asyncio.Queue = asyncio.Queue()
        self._channels.setdefault(channel, []).append(q)
        return MockSubscriber(self, channel, q)

    def unsubscribe(self, channel: str, q: asyncio.Queue):
        if channel in self._channels and q in self._channels[channel]:
            self._channels[channel].remove(q)


class MockSubscriber:
    def __init__(self, broker: MockRedisPubSub, channel: str, queue: asyncio.Queue):
        self.broker = broker
        self.channel = channel
        self.queue = queue

    async def get_message(self, timeout: float = 1.0) -> dict | None:
        try:
            data = await asyncio.wait_for(self.queue.get(), timeout=timeout)
            return {"type": "message", "channel": self.channel, "data": data}
        except asyncio.TimeoutError:
            return None

    def close(self):
        self.broker.unsubscribe(self.channel, self.queue)


@pytest.mark.asyncio
async def test_publisher_events_payload():
    """Verify StreamEventPublisher emits properly formatted JSON events."""
    published_events = []

    mock_client = AsyncMock()

    async def mock_publish(channel, payload):
        published_events.append((channel, json.loads(payload)))
        return 1

    mock_client.publish.side_effect = mock_publish

    publisher = StreamEventPublisher(
        session_id=42,
        redis_client=mock_client,
    )

    # 1. Status event
    await publisher.publish_status("pii_scan", "Scanning message for sensitive data...")
    # 2. Tool call start & end
    await publisher.publish_tool_start("get_balance", "Executing get_balance...")
    await publisher.publish_tool_end("get_balance", success=True)
    # 3. Token chunk
    await publisher.publish_token("Hello world")
    # 4. Done event
    await publisher.publish_done(
        reply="Hello world",
        tools_called=["get_balance"],
        intent="accounts",
    )
    # 5. Error event
    await publisher.publish_error("Something went wrong")

    assert len(published_events) == 6
    assert all(channel == "stream:42" for channel, _ in published_events)

    events = [payload for _, payload in published_events]
    assert events[0]["type"] == "status"
    assert events[0]["stage"] == "pii_scan"

    assert events[1]["type"] == "tool_call_start"
    assert events[1]["tool_name"] == "get_balance"

    assert events[2]["type"] == "tool_call_end"
    assert events[2]["tool_name"] == "get_balance"
    assert events[2]["success"] is True

    assert events[3]["type"] == "token"
    assert events[3]["token"] == "Hello world"

    assert events[4]["type"] == "done"
    assert events[4]["reply"] == "Hello world"
    assert events[4]["tools_called"] == ["get_balance"]
    assert events[4]["intent"] == "accounts"

    assert events[5]["type"] == "error"
    assert events[5]["error"] == "Something went wrong"


@pytest.mark.asyncio
async def test_auto_scaling_simulation_multiple_backend_subscribers():
    """
    Simulate auto-scaling across multiple independent backend instances:
    1 AI Service publisher publishes to Redis Pub/Sub channel `stream:101`.
    2 independent Django backend instances (Worker #1 and Worker #2) are subscribed
    to the same Redis channel, each proxying to its client.

    Both backend instances must receive all streamed events in real time without loss,
    demonstrating full decoupling and auto-scaling resilience.
    """
    broker = MockRedisPubSub()

    # Simulate Instance 1 (Django Worker 1)
    sub1 = broker.subscribe("stream:101")
    # Simulate Instance 2 (Django Worker 2)
    sub2 = broker.subscribe("stream:101")

    # Simulate AI Service publisher
    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = broker.publish
    publisher = StreamEventPublisher(session_id=101, redis_client=mock_redis)

    # Stream a sequence of events
    await publisher.publish_status("pii_scan", "Scanning message...")
    await publisher.publish_status("routing", "Selecting banking sub-agent...")
    await publisher.publish_tool_start("get_balance")
    await publisher.publish_tool_end("get_balance", success=True)
    await publisher.publish_token("Your ")
    await publisher.publish_token("balance ")
    await publisher.publish_token("is $5,000.00 USD.")
    await publisher.publish_done(
        reply="Your balance is $5,000.00 USD.",
        tools_called=["get_balance"],
        intent="accounts",
    )

    # Collect events received by Instance 1
    events1 = []
    for _ in range(8):
        msg = await sub1.get_message(timeout=1.0)
        assert msg is not None
        events1.append(json.loads(msg["data"]))

    # Collect events received by Instance 2
    events2 = []
    for _ in range(8):
        msg = await sub2.get_message(timeout=1.0)
        assert msg is not None
        events2.append(json.loads(msg["data"]))

    # Both independent instances must have received the identical event sequence
    assert len(events1) == 8
    assert len(events2) == 8
    assert events1 == events2

    # Check event order and structure
    event_types = [e["type"] for e in events1]
    assert event_types == [
        "status",
        "status",
        "tool_call_start",
        "tool_call_end",
        "token",
        "token",
        "token",
        "done",
    ]

    tokens = "".join([e["token"] for e in events1 if e["type"] == "token"])
    assert tokens == "Your balance is $5,000.00 USD."

    sub1.close()
    sub2.close()


@pytest.mark.asyncio
async def test_auto_scaling_subscriber_disconnect_resilience():
    """Verify that if one instance crashes/disconnects, remaining instances continue receiving."""
    broker = MockRedisPubSub()

    sub_survivor = broker.subscribe("stream:202")
    sub_doomed = broker.subscribe("stream:202")

    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = broker.publish
    publisher = StreamEventPublisher(session_id=202, redis_client=mock_redis)

    # First event received by both
    await publisher.publish_status("pii_scan", "Scanning...")
    m1 = await sub_survivor.get_message(timeout=1.0)
    m2 = await sub_doomed.get_message(timeout=1.0)
    assert m1 is not None and m2 is not None

    # Instance 2 disconnects / crashes
    sub_doomed.close()

    # Second event sent
    await publisher.publish_token("Chunk after crash")

    # Survivor continues without issue
    m_survivor = await sub_survivor.get_message(timeout=1.0)
    assert m_survivor is not None
    assert json.loads(m_survivor["data"])["token"] == "Chunk after crash"

    # Doomed subscriber queue is closed and does not receive new message
    m_doomed = await sub_doomed.get_message(timeout=0.1)
    assert m_doomed is None

    sub_survivor.close()


@pytest.mark.asyncio
async def test_tool_execution_publishes_tool_start_and_end():
    """Verify tool invocation emits tool_call_start and tool_call_end through the publisher."""
    from mcp_client import DiscoveredMCPTool, StructuredTool, bind_mcp_tools_for_user

    published_events = []
    mock_client = AsyncMock()

    async def mock_publish(channel, payload):
        published_events.append(json.loads(payload))
        return 1

    mock_client.publish.side_effect = mock_publish
    publisher = StreamEventPublisher(session_id=77, redis_client=mock_client)

    async def fake_balance(user_id: int):
        return '{"balance": 1500.0, "currency": "USD"}'

    raw_tool = StructuredTool.from_function(
        coroutine=fake_balance,
        name="get_balance",
        description="Check balance",
        args_schema={"type": "object", "properties": {"user_id": {"type": "integer"}}},
    )

    discovered = [DiscoveredMCPTool(server_name="accounts", tool=raw_tool)]
    bound = bind_mcp_tools_for_user(
        discovered,
        user_id=1,
        role="customer",
        publisher=publisher,
    )

    result = await bound[0].ainvoke({})
    assert "1500.0" in result

    types = [e["type"] for e in published_events]
    assert "tool_call_start" in types
    assert "tool_call_end" in types

    start_event = next(e for e in published_events if e["type"] == "tool_call_start")
    end_event = next(e for e in published_events if e["type"] == "tool_call_end")

    assert start_event["tool_name"] == "get_balance"
    assert end_event["tool_name"] == "get_balance"
    assert end_event["success"] is True


@pytest.mark.asyncio
async def test_coordinator_publishes_streaming_events():
    """Verify coordinator graph emits status and streaming tokens when executed with publisher."""
    pytest.importorskip("langchain_core")

    from agents.coordinator import IntentClassification, build_coordinator_graph
    from agents.base import AIMessageStub, BaseChatModelStub

    published_events = []
    mock_client = AsyncMock()

    async def mock_publish(channel, payload):
        published_events.append(json.loads(payload))
        return 1

    mock_client.publish.side_effect = mock_publish
    publisher = StreamEventPublisher(session_id=88, redis_client=mock_client)

    class FakeLLM(BaseChatModelStub):
        def with_structured_output(self, schema, **kwargs):
            structured = MagicMock()
            structured.ainvoke = AsyncMock(
                return_value=IntentClassification(
                    intent="accounts",
                    confidence=0.95,
                    reason="User asked for account balance.",
                )
            )
            return structured

        async def ainvoke(self, messages, **kwargs):
            return AIMessageStub(content="Your balance is $2,500.00 USD.")

    graph = build_coordinator_graph(
        llm=FakeLLM(),
        tools={},
        publisher=publisher,
    )

    from langchain_core.messages import HumanMessage
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="What is my balance?")],
            "user_id": 1,
            "role": "customer",
            "session_id": 88,
            "account_number": "FC100",
            "intent": "",
            "confidence": 0.0,
            "reason": "",
            "reply": "",
            "tools_called": [],
            "llm_calls": [],
            "traces": [],
        }
    )

    assert "2,500.00" in result["reply"]

    types = [e["type"] for e in published_events]
    assert "status" in types
    assert "token" in types

    routing_event = next(e for e in published_events if e.get("stage") == "routing")
    routed_event = next(e for e in published_events if e.get("stage") == "routed")
    assert routing_event is not None
    assert routed_event["intent"] == "accounts"

    tokens = "".join([e["token"] for e in published_events if e["type"] == "token"])
    assert "Your balance is $2,500.00 USD." == tokens

