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
    import time

    import redis.asyncio as aioredis
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

        reasons = (
            await session.execute(
                select(Url.failure_reason, func.count(Url.id))
                .where(Url.status == UrlStatus.FAILED)
                .where(Url.failure_reason.isnot(None))
                .group_by(Url.failure_reason)
                .order_by(func.count(Url.id).desc())
                .limit(10)
            )
        ).all()
        failure_reasons = {r: c for r, c in reasons}

    indexed = await search_index.count()

    crawl_rate = 0.0
    dedup_hits = 0
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        now = time.time()
        recent = await r.lrange("crawler:recent_crawls", 0, -1)
        if recent:
            timestamps = [float(t) for t in recent]
            window_start = now - 60
            in_window = [t for t in timestamps if t >= window_start]
            crawl_rate = len(in_window) / 60.0 if in_window else 0.0
        dedup_str = await r.get("crawler:dedup_hits")
        dedup_hits = int(dedup_str) if dedup_str else 0
        await r.aclose()
    except Exception:
        pass

    return {
        "pages_crawled": crawled,
        "pages_failed": failed,
        "queue_size": pending,
        "crawl_rate": round(crawl_rate, 2),
        "dedup_hits": dedup_hits,
        "indexed_pages": indexed,
        "total_urls": total,
        "failure_reasons": failure_reasons,
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
