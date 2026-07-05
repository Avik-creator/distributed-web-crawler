from __future__ import annotations

import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str
    size: int = 10


class SearchHit(BaseModel):
    url: str
    title: str
    host: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHit]
    total: int


class EnqueueRequest(BaseModel):
    urls: list[str]
    max_depth: int | None = None


class EnqueueResponse(BaseModel):
    queued: int
    urls: list[str]


class StatsResponse(BaseModel):
    pages_indexed: int
    crawl_delay_default: float
    max_concurrent_requests: int
    max_depth: int
    elasticsearch_index: str
    timestamp: str
