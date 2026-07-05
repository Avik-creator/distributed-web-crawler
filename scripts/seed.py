import asyncio
import logging

from src.worker_app import Crawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SEED_URLS = [
    "https://example.com",
]


async def seed() -> None:
    crawler = Crawler()
    await crawler.run(seed_urls=SEED_URLS, max_pages=20)


if __name__ == "__main__":
    asyncio.run(seed())
