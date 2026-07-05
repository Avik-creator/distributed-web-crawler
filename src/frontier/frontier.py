import logging

from src.frontier.normalizer import extract_host, normalize_url
from src.storage.metadata import MetadataStore

logger = logging.getLogger(__name__)


class Frontier:
    def __init__(self) -> None:
        self.metadata = MetadataStore()

    async def enqueue(
        self,
        url: str,
        base_url: str | None = None,
        priority: int = 50,
        depth: int = 0,
    ) -> bool:
        normalized = normalize_url(url, base_url)
        if not normalized:
            logger.debug("Skipping invalid URL: %s", url)
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

        logger.info("Enqueued: %s (host=%s, depth=%d)", normalized, host, depth)
        return True

    async def dequeue(self, limit: int = 5) -> list[dict]:
        pending = await self.metadata.get_pending_urls(limit)
        results = []
        for url_record in pending:
            await self.metadata.mark_crawling(url_record.id)
            results.append(
                {
                    "id": url_record.id,
                    "url": url_record.url,
                    "normalized_url": url_record.normalized_url,
                    "host": url_record.host,
                    "depth": url_record.depth,
                }
            )
        return results
