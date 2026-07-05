import logging
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

HOST_KEY_PREFIX = "host_next:"
DEFAULT_CRAWL_DELAY = 1.0


class Scheduler:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def can_crawl(self, host: str, crawl_delay: float | None = None) -> bool:
        key = f"{HOST_KEY_PREFIX}{host}"

        next_time_str = await self.redis.get(key)
        if next_time_str is None:
            return True

        next_time = datetime.fromisoformat(next_time_str)
        return datetime.now(UTC) >= next_time

    async def mark_crawled(self, host: str, crawl_delay: float | None = None) -> None:
        delay = crawl_delay if crawl_delay is not None else DEFAULT_CRAWL_DELAY
        key = f"{HOST_KEY_PREFIX}{host}"
        next_time = datetime.now(UTC) + timedelta(seconds=delay)
        await self.redis.set(key, next_time.isoformat())

    async def wait_for_slot(self, host: str, crawl_delay: float | None = None) -> float:
        key = f"{HOST_KEY_PREFIX}{host}"

        next_time_str = await self.redis.get(key)
        if next_time_str is None:
            return 0.0

        next_time = datetime.fromisoformat(next_time_str)
        now = datetime.now(UTC)
        wait_seconds = (next_time - now).total_seconds()
        return max(0.0, wait_seconds)
