import asyncio
import logging

from src.config import settings
from src.crawler.downloader import Downloader, DownloadError
from src.crawler.parser import parse_html
from src.frontier.frontier import Frontier
from src.models.db import init_db
from src.storage.metadata import MetadataStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self) -> None:
        self.frontier = Frontier()
        self.downloader = Downloader()
        self.metadata = MetadataStore()
        self.max_depth = settings.max_depth

    async def crawl_url(self, url_record: dict) -> list[str]:
        url = url_record["normalized_url"]
        url_id = url_record["id"]
        depth = url_record["depth"]

        logger.info("Crawling: %s (depth=%d)", url, depth)

        try:
            result = await self.downloader.download(url)
        except DownloadError as exc:
            logger.warning("Failed to download %s: %s", url, exc)
            await self.metadata.mark_failed(url_id)
            return []

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
                enqueued = await self.frontier.enqueue(
                    link,
                    base_url=url,
                    depth=depth + 1,
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

        logger.info("Seeding %d URLs", len(seed_urls))
        for url in seed_urls:
            await self.frontier.enqueue(url, priority=100)

        pages_crawled = 0
        while pages_crawled < max_pages:
            batch = await self.frontier.dequeue(limit=settings.max_concurrent_requests)
            if not batch:
                logger.info("No more URLs to crawl.")
                break

            tasks = [self.crawl_url(record) for record in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error("Task failed: %s", result)
                else:
                    pages_crawled += len(result) if result else 1

            logger.info("Progress: %d pages crawled", pages_crawled)

        await self.downloader.close()
        logger.info("Crawl complete. Total pages crawled: %d", pages_crawled)


async def main() -> None:
    crawler = Crawler()
    await crawler.run(
        seed_urls=["https://example.com"],
        max_pages=50,
    )


if __name__ == "__main__":
    asyncio.run(main())
