import logging
from urllib.parse import urlparse

import aiohttp
import redis.asyncio as aioredis
from robotexclusionrulesparser import RobotExclusionRulesParser

from src.config import settings

logger = logging.getLogger(__name__)

ROBOTS_KEY_PREFIX = "robots:"
ROBOTS_CACHE_TTL = settings.robots_cache_ttl


class RobotsCache:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def is_allowed(self, url: str, user_agent: str | None = None) -> bool:
        ua = user_agent or settings.user_agent
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        rules = await self._get_rules(robots_url)
        if rules is None:
            return True

        return rules.is_allowed(ua, url)

    async def get_crawl_delay(self, url: str, user_agent: str | None = None) -> float | None:
        ua = user_agent or settings.user_agent
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        rules = await self._get_rules(robots_url)
        if rules is None:
            return None

        delay = rules.get_crawl_delay(ua)
        return float(delay) if delay else None

    async def _get_rules(self, robots_url: str) -> RobotExclusionRulesParser | None:
        cached = await self.redis.get(f"{ROBOTS_KEY_PREFIX}{robots_url}")
        if cached is not None:
            if cached == b"":
                return None
            rules = RobotExclusionRulesParser()
            rules.parse(cached.decode())
            return rules

        rules = await self._fetch_and_cache(robots_url)
        return rules

    async def _fetch_and_cache(self, robots_url: str) -> RobotExclusionRulesParser | None:
        try:
            async with (
                aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session,
                session.get(robots_url) as resp,
            ):
                if resp.status == 404:
                    await self.redis.setex(
                        f"{ROBOTS_KEY_PREFIX}{robots_url}", ROBOTS_CACHE_TTL, ""
                    )
                    return None
                if resp.status >= 400:
                    return None
                content = await resp.text()
        except Exception:
            logger.warning("Failed to fetch robots.txt: %s", robots_url)
            return None

        rules = RobotExclusionRulesParser()
        rules.parse(content)

        await self.redis.setex(
            f"{ROBOTS_KEY_PREFIX}{robots_url}", ROBOTS_CACHE_TTL, content
        )
        logger.info("Cached robots.txt for %s", robots_url)
        return rules
