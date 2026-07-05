import json
import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

QUEUE_KEY = "crawl_queue"


class PriorityQueue:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def push(
        self,
        url_id: int,
        normalized_url: str,
        host: str,
        priority: int = 50,
        depth: int = 0,
    ) -> None:
        member = json.dumps(
            {
                "id": url_id,
                "url": normalized_url,
                "host": host,
                "depth": depth,
            }
        )
        await self.redis.zadd(QUEUE_KEY, {member: priority})
        logger.debug("Pushed URL %d with priority %d", url_id, priority)

    async def pop(self, count: int = 1) -> list[dict]:
        results: list[dict] = []
        for _ in range(count):
            items = await self.redis.zpopmax(QUEUE_KEY, count=1)
            if not items:
                break
            member, _score = items[0]
            data = json.loads(member)
            results.append(data)
        return results

    async def peek(self, count: int = 10) -> list[dict]:
        items = await self.redis.zrevrange(QUEUE_KEY, 0, count - 1)
        results = []
        for member in items:
            data = json.loads(member)
            results.append(data)
        return results

    async def size(self) -> int:
        return await self.redis.zcard(QUEUE_KEY)
