from __future__ import annotations

import logging

import aiohttp

from src.config import settings

logger = logging.getLogger(__name__)

MAPPINGS = {
    "mappings": {
        "properties": {
            "url": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "standard"},
            "body": {"type": "text", "analyzer": "standard"},
            "host": {"type": "keyword"},
            "crawled_at": {"type": "date"},
            "status_code": {"type": "integer"},
        }
    }
}


class SearchIndex:
    def __init__(self) -> None:
        self.base_url = settings.elasticsearch_url
        self.index = settings.elasticsearch_index

    async def _request(self, method: str, path: str, **kwargs: object) -> dict:
        url = f"{self.base_url}{path}"
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.request(method, url, **kwargs) as resp,
            ):
                if resp.status >= 400:
                    text = await resp.text()
                    logger.warning(
                        "ES %s %s returned %d: %s", method, path, resp.status, text
                    )
                    return {}
                return await resp.json()
        except aiohttp.ClientError:
            logger.debug("Elasticsearch unavailable: %s %s", method, path)
            return {}

    async def ensure_index(self) -> None:
        exists = await self._request("HEAD", f"/{self.index}")
        if not exists:
            await self._request("PUT", f"/{self.index}", json=MAPPINGS)
            logger.info("Created Elasticsearch index: %s", self.index)

    async def index_page(
        self,
        url: str,
        title: str,
        body: str,
        host: str,
        crawled_at: str,
        status_code: int = 200,
    ) -> None:
        doc = {
            "url": url,
            "title": title,
            "body": body[:10000],
            "host": host,
            "crawled_at": crawled_at,
            "status_code": status_code,
        }
        await self._request(
            "POST",
            f"/{self.index}/_doc",
            json=doc,
        )
        logger.debug("Indexed page: %s", url)

    async def search(self, query: str, size: int = 10) -> list[dict]:
        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "body"],
                }
            },
            "size": size,
            "_source": ["url", "title", "host", "crawled_at"],
        }
        result = await self._request("POST", f"/{self.index}/_search", json=body)
        hits = result.get("hits", {}).get("hits", [])
        return [
            {
                "url": hit["_source"]["url"],
                "title": hit["_source"]["title"],
                "host": hit["_source"].get("host", ""),
                "score": hit["_score"],
            }
            for hit in hits
        ]

    async def count(self) -> int:
        result = await self._request("GET", f"/{self.index}/_count")
        return result.get("count", 0)
