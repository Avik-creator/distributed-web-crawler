from __future__ import annotations

import pytest
import redis.asyncio as aioredis

from src.frontier.stream_queue import StreamQueue


@pytest.fixture
async def redis_client():
    client = aioredis.from_url("redis://localhost:6379/1", decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


class TestStreamQueue:
    async def test_push_and_pop(self, redis_client: aioredis.Redis) -> None:
        queue = StreamQueue(redis_client)
        await queue.init_group()
        await queue.push(1, "https://a.com", "a.com", priority=100, depth=0)

        messages = await queue.pop("test_consumer", count=1, block=100)
        assert len(messages) == 1
        assert messages[0]["id"] == 1
        assert messages[0]["url"] == "https://a.com"

    async def test_ack_removes_message(self, redis_client: aioredis.Redis) -> None:
        queue = StreamQueue(redis_client)
        await queue.init_group()
        await queue.push(1, "https://a.com", "a.com")

        messages = await queue.pop("test_consumer", count=1, block=100)
        assert len(messages) == 1
        await queue.ack(messages[0]["stream_id"])

        messages2 = await queue.pop("test_consumer", count=1, block=100)
        assert len(messages2) == 0

    async def test_multiple_consumers(self, redis_client: aioredis.Redis) -> None:
        queue = StreamQueue(redis_client)
        await queue.init_group()
        await queue.push(1, "https://a.com", "a.com")
        await queue.push(2, "https://b.com", "b.com")

        msgs1 = await queue.pop("worker_1", count=1, block=100)
        msgs2 = await queue.pop("worker_2", count=1, block=100)
        assert len(msgs1) == 1
        assert len(msgs2) == 1
        assert msgs1[0]["id"] != msgs2[0]["id"]

    async def test_pop_empty(self, redis_client: aioredis.Redis) -> None:
        queue = StreamQueue(redis_client)
        await queue.init_group()
        messages = await queue.pop("test_consumer", count=5, block=100)
        assert messages == []
