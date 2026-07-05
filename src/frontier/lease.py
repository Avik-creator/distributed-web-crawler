import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

LEASE_PREFIX = "lease:"
DEFAULT_LEASE_TTL = 300


class Leasing:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def acquire(self, url_id: int, ttl: int | None = None) -> bool:
        lease_ttl = ttl or DEFAULT_LEASE_TTL
        key = f"{LEASE_PREFIX}{url_id}"
        result = await self.redis.set(key, "1", nx=True, ex=lease_ttl)
        if result:
            logger.debug("Leased URL %d for %ds", url_id, lease_ttl)
            return True
        logger.debug("URL %d already leased", url_id)
        return False

    async def release(self, url_id: int) -> None:
        key = f"{LEASE_PREFIX}{url_id}"
        await self.redis.delete(key)
        logger.debug("Released lease for URL %d", url_id)

    async def is_leased(self, url_id: int) -> bool:
        key = f"{LEASE_PREFIX}{url_id}"
        return await self.redis.exists(key) > 0
