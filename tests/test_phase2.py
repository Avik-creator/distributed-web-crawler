import asyncio

import pytest
import redis.asyncio as aioredis

from src.frontier.dedup import Deduplicator
from src.frontier.lease import Leasing
from src.frontier.priority_queue import PriorityQueue
from src.frontier.scheduler import Scheduler


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def redis_client():
    client = aioredis.from_url("redis://localhost:6379/1", decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


class TestPriorityQueue:
    async def test_push_and_pop(self, redis_client: aioredis.Redis) -> None:
        queue = PriorityQueue(redis_client)
        await queue.push(1, "https://a.com", "a.com", priority=100)
        await queue.push(2, "https://b.com", "b.com", priority=50)

        items = await queue.pop(count=1)
        assert len(items) == 1
        assert items[0]["id"] == 1
        assert items[0]["url"] == "https://a.com"

    async def test_pop_order(self, redis_client: aioredis.Redis) -> None:
        queue = PriorityQueue(redis_client)
        await queue.push(1, "https://low.com", "low.com", priority=10)
        await queue.push(2, "https://high.com", "high.com", priority=100)
        await queue.push(3, "https://mid.com", "mid.com", priority=50)

        items = await queue.pop(count=3)
        ids = [i["id"] for i in items]
        assert ids == [2, 3, 1]

    async def test_size(self, redis_client: aioredis.Redis) -> None:
        queue = PriorityQueue(redis_client)
        assert await queue.size() == 0
        await queue.push(1, "https://a.com", "a.com")
        assert await queue.size() == 1

    async def test_pop_empty(self, redis_client: aioredis.Redis) -> None:
        queue = PriorityQueue(redis_client)
        items = await queue.pop(count=5)
        assert items == []


class TestScheduler:
    async def test_first_crawl_allowed(self, redis_client: aioredis.Redis) -> None:
        scheduler = Scheduler(redis_client)
        assert await scheduler.can_crawl("example.com") is True

    async def test_mark_crawled_enforces_delay(self, redis_client: aioredis.Redis) -> None:
        scheduler = Scheduler(redis_client)
        await scheduler.mark_crawled("example.com", crawl_delay=10)
        assert await scheduler.can_crawl("example.com", crawl_delay=10) is False

    async def test_wait_returns_positive(self, redis_client: aioredis.Redis) -> None:
        scheduler = Scheduler(redis_client)
        await scheduler.mark_crawled("example.com", crawl_delay=5)
        wait = await scheduler.wait_for_slot("example.com", crawl_delay=5)
        assert wait > 0


class TestLeasing:
    async def test_acquire_and_release(self, redis_client: aioredis.Redis) -> None:
        lease = Leasing(redis_client)
        assert await lease.acquire(1) is True
        assert await lease.is_leased(1) is True
        await lease.release(1)
        assert await lease.is_leased(1) is False

    async def test_double_acquire_fails(self, redis_client: aioredis.Redis) -> None:
        lease = Leasing(redis_client)
        assert await lease.acquire(1) is True
        assert await lease.acquire(1) is False
        await lease.release(1)

    async def test_lease_ttl(self, redis_client: aioredis.Redis) -> None:
        lease = Leasing(redis_client)
        assert await lease.acquire(1, ttl=1) is True
        assert await lease.is_leased(1) is True
        await asyncio.sleep(1.1)
        assert await lease.is_leased(1) is False


class TestDeduplicator:
    async def test_add_and_check(self, redis_client: aioredis.Redis) -> None:
        dedup = Deduplicator(redis_client)
        assert await dedup.add_and_check("hash1") is False
        assert await dedup.add_and_check("hash1") is True

    async def test_separate_hashes(self, redis_client: aioredis.Redis) -> None:
        dedup = Deduplicator(redis_client)
        assert await dedup.add_and_check("hash_a") is False
        assert await dedup.add_and_check("hash_b") is False
        assert await dedup.add_and_check("hash_a") is True
