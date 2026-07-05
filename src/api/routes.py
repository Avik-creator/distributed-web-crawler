from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from src.api.models import (
    EnqueueRequest,
    EnqueueResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    StatsResponse,
)
from src.config import settings
from src.storage.search_index import SearchIndex

logger = logging.getLogger(__name__)

router = APIRouter()
search_index = SearchIndex()
DASHBOARD_PATH = Path(__file__).parent.parent / "static" / "index.html"


@router.on_event("startup")
async def startup() -> None:
    await search_index.ensure_index()


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    hits = await search_index.search(request.query, size=request.size)
    return SearchResponse(
        query=request.query,
        results=[SearchHit(**hit) for hit in hits],
        total=len(hits),
    )


@router.post("/urls", response_model=EnqueueResponse)
async def enqueue_urls(request: EnqueueRequest) -> EnqueueResponse:
    from src.worker_app import Worker

    worker = Worker(worker_id="api_enqueuer")
    await worker._init_redis()

    queued = 0
    for url in request.urls:
        success = await worker.enqueue_url(url, priority=100)
        if success:
            queued += 1

    if worker.redis:
        await worker.redis.aclose()

    return EnqueueResponse(queued=queued, urls=request.urls)


@router.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    count = await search_index.count()
    return StatsResponse(
        pages_indexed=count,
        crawl_delay_default=settings.crawl_delay_default,
        max_concurrent_requests=settings.max_concurrent_requests,
        max_depth=settings.max_depth,
        elasticsearch_index=settings.elasticsearch_index,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/health")
async def health() -> dict:
    import aiohttp

    checks = {"api": "ok", "redis": "unknown", "elasticsearch": "unknown"}

    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    try:
        async with aiohttp.ClientSession() as session, session.get(
            f"{settings.elasticsearch_url}/_cluster/health"
        ) as resp:
                if resp.status == 200:
                    checks["elasticsearch"] = "ok"
                else:
                    checks["elasticsearch"] = "error"
    except Exception:
        checks["elasticsearch"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if all_ok else "degraded", "checks": checks}


@router.get("/metrics")
async def metrics() -> dict:
    from sqlalchemy import func, select

    from src.models.db import Url, UrlStatus, async_session

    async with async_session() as session:
        total = (await session.execute(select(func.count(Url.id)))).scalar() or 0
        crawled = (
            await session.execute(
                select(func.count(Url.id)).where(Url.status == UrlStatus.CRAWLED)
            )
        ).scalar() or 0
        failed = (
            await session.execute(
                select(func.count(Url.id)).where(Url.status == UrlStatus.FAILED)
            )
        ).scalar() or 0
        pending = (
            await session.execute(
                select(func.count(Url.id)).where(Url.status == UrlStatus.PENDING)
            )
        ).scalar() or 0

    indexed = await search_index.count()

    return {
        "pages_crawled": crawled,
        "pages_failed": failed,
        "queue_size": pending,
        "crawl_rate": 0.0,
        "dedup_hits": 0,
        "indexed_pages": indexed,
        "total_urls": total,
        "robots_cache_hits": 0,
        "robots_cache_misses": 0,
    }


@router.get("/ui", response_class=HTMLResponse)
async def ui() -> str:
    return DASHBOARD_PATH.read_text()


@router.get("/pages/{url:path}")
async def get_page(url: str) -> dict:
    result = await search_index.search(url, size=1)
    if not result:
        return {"error": "Page not found"}
    return result[0]
