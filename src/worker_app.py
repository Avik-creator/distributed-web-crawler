from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import signal
import time
from datetime import UTC, datetime

import redis.asyncio as aioredis

from src.config import settings
from src.crawler.downloader import Downloader, DownloadError
from src.crawler.parser import parse_html
from src.crawler.robots import RobotsCache
from src.crawler.simhash import is_near_duplicate, simhash
from src.frontier.dedup import Deduplicator
from src.frontier.lease import Leasing
from src.frontier.normalizer import extract_host, normalize_url
from src.frontier.scheduler import Scheduler
from src.frontier.stream_queue import StreamQueue
from src.models.db import init_db
from src.storage.metadata import MetadataStore
from src.storage.search_index import SearchIndex

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CONSUMER_PREFIX = "worker"


class Worker:
    def __init__(self, worker_id: str | None = None) -> None:
        self.worker_id = worker_id or f"{CONSUMER_PREFIX}_{os.getpid()}"
        self.downloader = Downloader()
        self.metadata = MetadataStore()
        self.search_index = SearchIndex()
        self.max_depth = settings.max_depth
        self.redis: aioredis.Redis | None = None
        self.robots: RobotsCache | None = None
        self.scheduler: Scheduler | None = None
        self.lease: Leasing | None = None
        self.stream: StreamQueue | None = None
        self.dedup: Deduplicator | None = None
        self._shutting_down = False
        self._content_hashes: set[int] = set()
        self._etag_cache: dict[str, str] = {}

    async def _init_redis(self) -> None:
        self.redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=30,
            socket_connect_timeout=10,
        )
        self.robots = RobotsCache(self.redis)
        self.scheduler = Scheduler(self.redis)
        self.lease = Leasing(self.redis)
        self.stream = StreamQueue(self.redis)
        self.dedup = Deduplicator(self.redis)
        await self.stream.init_group()
        await self.search_index.ensure_index()

    def _handle_signal(self, signum: int, _frame: object) -> None:
        sig_name = signal.Signals(signum).name
        logger.info(
            "Worker %s received %s, shutting down gracefully...",
            self.worker_id,
            sig_name,
        )
        self._shutting_down = True

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

        await self.stream.push(url_id, normalized, host, priority, depth)
        logger.info("Enqueued: %s (host=%s, depth=%d)", normalized, host, depth)
        return True

    async def crawl_url(self, url_record: dict) -> list[str]:
        url = url_record["url"]
        url_id = url_record["id"]
        stream_id = url_record["stream_id"]
        host = url_record["host"]
        depth = url_record["depth"]

        if not await self.lease.acquire(url_id):
            logger.debug("URL %d already leased, skipping", url_id)
            await self.stream.ack(stream_id)
            return []

        try:
            if not await self.robots.is_allowed(url):
                logger.info("Blocked by robots.txt: %s", url)
                await self.metadata.mark_failed(url_id)
                return []

            crawl_delay = await self.robots.get_crawl_delay(url)
            if crawl_delay is not None:
                wait = await self.scheduler.wait_for_slot(host, crawl_delay)
                if wait > 0:
                    logger.debug("Waiting %.1fs for %s crawl-delay", wait, host)
                    await asyncio.sleep(wait)

            etag = self._etag_cache.get(url)
            logger.info("Crawling: %s (depth=%d)", url, depth)
            result = await self.downloader.download(url, etag=etag)

            if result.status_code == 304:
                logger.info("Not modified: %s (using ETag)", url)
                await self.metadata.mark_crawled(url_id)
                await self.stream.ack(stream_id)
                return []

            if crawl_delay is not None:
                await self.scheduler.mark_crawled(host, crawl_delay)

        except DownloadError as exc:
            if exc.status_code == 304:
                logger.info("Not modified: %s", url)
                await self.metadata.mark_crawled(url_id)
                await self.stream.ack(stream_id)
                return []
            logger.warning("Failed to download %s: %s", url, exc)
            await self.metadata.mark_failed(url_id)
            return []
        finally:
            await self.lease.release(url_id)

        content_hash = simhash(result.html)
        if content_hash in self._content_hashes:
            logger.info("Duplicate content: %s", url)
            await self.metadata.mark_crawled(url_id)
            await self.stream.ack(stream_id)
            return []
        for existing_hash in self._content_hashes:
            if is_near_duplicate(content_hash, existing_hash):
                logger.info("Near-duplicate content: %s", url)
                await self.metadata.mark_crawled(url_id)
                await self.stream.ack(stream_id)
                return []
        self._content_hashes.add(content_hash)

        if result.etag:
            self._etag_cache[url] = result.etag

        title, links = parse_html(result.html, base_url=url)

        await self.metadata.store_page(
            url_id=url_id,
            html=result.html,
            title=title,
            status_code=result.status_code,
            etag=result.etag,
        )
        await self.metadata.mark_crawled(url_id)
        await self.stream.ack(stream_id)

        await self.search_index.index_page(
            url=url,
            title=title,
            body=result.html[:10000],
            host=host,
            crawled_at=datetime.now(UTC).isoformat(),
            status_code=result.status_code,
        )

        new_urls: list[str] = []
        if depth < self.max_depth:
            for link in links:
                enqueued = await self.enqueue_url(
                    link, base_url=url, depth=depth + 1
                )
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

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info("Worker %s starting", self.worker_id)
        logger.info("Seeding %d URLs", len(seed_urls))
        for url in seed_urls:
            await self.enqueue_url(url, priority=100)

        pages_crawled = 0
        start_time = time.monotonic()

        while pages_crawled < max_pages and not self._shutting_down:
            batch = await self.stream.pop(
                consumer=self.worker_id,
                count=settings.max_concurrent_requests,
                block=2000,
            )
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

            queue_size = await self.stream.size()
            elapsed = time.monotonic() - start_time
            rate = pages_crawled / elapsed if elapsed > 0 else 0
            logger.info(
                "Progress: %d pages crawled | queue=%d | rate=%.1f pages/s",
                pages_crawled,
                queue_size,
                rate,
            )

        if self._shutting_down:
            logger.info(
                "Worker %s shut down gracefully after %d pages",
                self.worker_id,
                pages_crawled,
            )
        else:
            logger.info(
                "Crawl complete. Total pages crawled: %d", pages_crawled
            )

        await self.downloader.close()
        if self.redis:
            await self.redis.aclose()

    async def run_consume(self) -> None:
        await init_db()
        await self._init_redis()

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info("Worker %s starting (consume mode)", self.worker_id)

        pages_crawled = 0
        start_time = time.monotonic()

        while not self._shutting_down:
            try:
                batch = await self.stream.pop(
                    consumer=self.worker_id,
                    count=settings.max_concurrent_requests,
                    block=5000,
                )
            except aioredis.ResponseError as exc:
                if "NOGROUP" in str(exc):
                    logger.warning("Consumer group lost, re-creating...")
                    await self.stream.init_group()
                    continue
                raise
            except (aioredis.TimeoutError, aioredis.ConnectionError) as exc:
                logger.warning("Redis read error: %s, retrying...", exc)
                await asyncio.sleep(2)
                continue

            if not batch:
                await asyncio.sleep(1)
                continue

            tasks = [self.crawl_url(record) for record in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error("Task failed: %s", result)
                else:
                    pages_crawled += 1

            qsize = await self.stream.size()
            elapsed = time.monotonic() - start_time
            rate = pages_crawled / elapsed if elapsed > 0 else 0
            logger.info(
                "Progress: %d pages crawled | queue=%d | rate=%.1f pages/s",
                pages_crawled,
                qsize,
                rate,
            )

        logger.info(
            "Worker %s shut down after %d pages",
            self.worker_id,
            pages_crawled,
        )
        await self.downloader.close()
        if self.redis:
            await self.redis.aclose()


async def main() -> None:
    worker = Worker()
    await worker.run_consume()


if __name__ == "__main__":
    asyncio.run(main())
