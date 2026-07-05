from __future__ import annotations

import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

STREAM_KEY = "crawl_stream"
RESULTS_STREAM_KEY = "crawl_results"
GROUP_NAME = "crawler_workers"
CONSUMER_PREFIX = "worker"


class StreamQueue:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def init_group(self) -> None:
        try:
            await self.redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
            logger.info("Created consumer group '%s' on stream '%s'", GROUP_NAME, STREAM_KEY)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def push(
        self,
        url_id: int,
        normalized_url: str,
        host: str,
        priority: int = 50,
        depth: int = 0,
    ) -> None:
        await self.redis.xadd(
            STREAM_KEY,
            {
                "id": str(url_id),
                "url": normalized_url,
                "host": host,
                "priority": str(priority),
                "depth": str(depth),
            },
        )
        logger.debug("Pushed URL %d to stream", url_id)

    async def pop(self, consumer: str, count: int = 1, block: int = 1000) -> list[dict]:
        results = await self.redis.xreadgroup(
            GROUP_NAME,
            consumer,
            {STREAM_KEY: ">"},
            count=count,
            block=block,
        )

        messages: list[dict] = []
        for _stream_name, entries in results:
            for entry_id, fields in entries:
                messages.append(
                    {
                        "stream_id": entry_id,
                        "id": int(fields["id"]),
                        "url": fields["url"],
                        "host": fields["host"],
                        "priority": int(fields["priority"]),
                        "depth": int(fields["depth"]),
                    }
                )
        return messages

    async def ack(self, *stream_ids: str) -> None:
        if stream_ids:
            await self.redis.xack(STREAM_KEY, GROUP_NAME, *stream_ids)

    async def size(self) -> int:
        info = await self.redis.xinfo_groups(STREAM_KEY)
        for group in info:
            if group["name"] == GROUP_NAME:
                return group["pending"]
        return 0
