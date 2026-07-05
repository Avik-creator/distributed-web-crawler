import asyncio
import hashlib
import logging
import time

import redis.asyncio as aioredis

from src.config import settings
from src.crawler.downloader import Downloader, DownloadError
from src.crawler.parser import parse_html
from src.crawler.robots import RobotsCache
from src.frontier.dedup import Deduplicator
from src.frontier.lease import Leasing
from src.frontier.normalizer import extract_host, normalize_url
from src.frontier.priority_queue import PriorityQueue
from src.frontier.scheduler import Scheduler
from src.models.db import init_db
from src.storage.metadata import MetadataStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self) -> None:
        self.downloader = Downloader()
        self.metadata = MetadataStore()
        self.max_depth = settings.max_depth
        self.redis: aioredis.Redis | None = None
        self.robots: RobotsCache | None = None
        self.scheduler: Scheduler | None = None
        self.lease: Leasing | None = None
        self.queue: PriorityQueue | None = None
        self.dedup: Deduplicator | None = None

    async def _init_redis(self) -> None:
        self.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        self.robots = RobotsCache(self.redis)
        self.scheduler = Scheduler(self.redis)
        self.lease = Leasing(self.redis)
        self.queue = PriorityQueue(self.redis)
        self.dedup = Deduplicator(self.redis)

    async def enqueue_url(
        self,
        url: str,
        base_url: str | None = None,
        priority: int = 50,
        depth: int = 0,
    ) -> bool:
        normalized = normalize_url(url, base_url)
        if not normalized:
            return False

        url_hash = hashlib.sha256(normalized.encode()).hexdigest()
        if await self.dedup.add_and_check(url_hash):
            return False

        host = extract_host(normalized)
        if not host:
            return False

        url_id = await self.metadata.add_url(
            url=url,
            normalized_url=normalized,
            host=host,
            priority=priority,
            depth=depth,
        )
        if url_id is None:
            return False

        await self.queue.push(url_id, normalized, host, priority, depth)
        logger.info("Enqueued: %s (host=%s, depth=%d)", normalized, host, depth)
        return True

    async def crawl_url(self, url_record: dict) -> list[str]:
        url = url_record["url"]
        url_id = url_record["id"]
        host = url_record["host"]
        depth = url_record["depth"]

        if not await self.lease.acquire(url_id):
            logger.debug("URL %d already leased, skipping", url_id)
            return []

        try:
            if not await self.robots.is_allowed(url):
                logger.info("Blocked by robots.txt: %s", url)
                await self.metadata.mark_failed(url_id)
                return []

            crawl_delay = await self.robots.get_crawl_delay(url)
            wait = await self.scheduler.wait_for_slot(host, crawl_delay)
            if wait > 0:
                logger.info("Waiting %.1fs for %s crawl-delay", wait, host)
                await asyncio.sleep(wait)

            logger.info("Crawling: %s (depth=%d)", url, depth)
            result = await self.downloader.download(url)

            await self.scheduler.mark_crawled(host, crawl_delay)

        except DownloadError as exc:
            logger.warning("Failed to download %s: %s", url, exc)
            await self.metadata.mark_failed(url_id)
            return []
        finally:
            await self.lease.release(url_id)

        title, links = parse_html(result.html, base_url=url)

        await self.metadata.store_page(
            url_id=url_id,
            html=result.html,
            title=title,
            status_code=result.status_code,
            etag=result.etag,
        )
        await self.metadata.mark_crawled(url_id)

        new_urls: list[str] = []
        if depth < self.max_depth:
            for link in links:
                enqueued = await self.enqueue_url(link, base_url=url, depth=depth + 1)
                if enqueued:
                    new_urls.append(link)

        logger.info(
            "Done: %s — title=%r, links=%d, new=%d",
            url,
            title[:50] if title else "",
            len(links),
            len(new_urls),
        )
        return new_urls

    async def run(self, seed_urls: list[str], max_pages: int = 100) -> None:
        await init_db()
        await self._init_redis()

        logger.info("Seeding %d URLs", len(seed_urls))
        for url in seed_urls:
            await self.enqueue_url(url, priority=100)

        pages_crawled = 0
        start_time = time.monotonic()

        while pages_crawled < max_pages:
            batch = await self.queue.pop(count=settings.max_concurrent_requests)
            if not batch:
                logger.info("No more URLs to crawl.")
                break

            tasks = [self.crawl_url(record) for record in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error("Task failed: %s", result)
                else:
                    pages_crawled += 1

            queue_size = await self.queue.size()
            elapsed = time.monotonic() - start_time
            rate = pages_crawled / elapsed if elapsed > 0 else 0
            logger.info(
                "Progress: %d pages crawled | queue=%d | rate=%.1f pages/s",
                pages_crawled,
                queue_size,
                rate,
            )

        await self.downloader.close()
        if self.redis:
            await self.redis.aclose()
        logger.info("Crawl complete. Total pages crawled: %d", pages_crawled)


async def main() -> None:
    crawler = Crawler()
    await crawler.run(
        seed_urls=["https://en.wikipedia.org/wiki/Web_crawler"],
        max_pages=10,
    )


if __name__ == "__main__":
    asyncio.run(main())
