from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter

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
    return {"status": "ok"}
