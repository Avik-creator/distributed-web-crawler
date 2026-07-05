from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from pybloom_live import BloomFilter

logger = logging.getLogger(__name__)

DEDUP_SET_KEY = "seen_urls"

try:
    from pybloom_live import BloomFilter as _BloomFilter

    BLOOM_AVAILABLE = True
except ImportError:
    BLOOM_AVAILABLE = False


class Deduplicator:
    def __init__(self, redis_client: aioredis.Redis, capacity: int = 1_000_000) -> None:
        self.redis = redis_client
        self.capacity = capacity
        self._bloom: BloomFilter | None = None

    def _get_bloom(self) -> BloomFilter | None:
        if BLOOM_AVAILABLE and self._bloom is None:
            self._bloom = _BloomFilter(capacity=self.capacity, error_rate=0.001)
        return self._bloom

    async def is_seen(self, url_hash: str) -> bool:
        bloom = self._get_bloom()
        if bloom is not None and url_hash in bloom:
            return True

        return await self.redis.sismember(DEDUP_SET_KEY, url_hash)

    async def mark_seen(self, url_hash: str) -> None:
        bloom = self._get_bloom()
        if bloom is not None:
            bloom.add(url_hash)

        await self.redis.sadd(DEDUP_SET_KEY, url_hash)

    async def add_and_check(self, url_hash: str) -> bool:
        bloom = self._get_bloom()
        if bloom is not None and url_hash in bloom:
            return True

        already_exists = await self.redis.sismember(DEDUP_SET_KEY, url_hash)
        if already_exists:
            return True

        await self.redis.sadd(DEDUP_SET_KEY, url_hash)
        if bloom is not None:
            bloom.add(url_hash)
        return False
