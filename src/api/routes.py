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
from src.metrics import (
    crawl_rate,
    dedup_hits,
    indexed_pages_total,
    pages_crawled_total,
    pages_failed_total,
    queue_size,
    robots_cache_hits,
    robots_cache_misses,
)
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
    def _counter_val(c: object) -> float:
        if hasattr(c, "_metrics") and c._metrics:  # type: ignore[attr-defined]
            return sum(m._value.get() for m in c._metrics.values())  # type: ignore[attr-defined]
        return 0.0

    return {
        "pages_crawled": _counter_val(pages_crawled_total),
        "pages_failed": _counter_val(pages_failed_total),
        "queue_size": queue_size._value.get(),
        "crawl_rate": crawl_rate._value.get(),
        "dedup_hits": _counter_val(dedup_hits),
        "indexed_pages": _counter_val(indexed_pages_total),
        "robots_cache_hits": _counter_val(robots_cache_hits),
        "robots_cache_misses": _counter_val(robots_cache_misses),
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
