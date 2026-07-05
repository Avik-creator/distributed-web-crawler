# Distributed Web Crawler

A fault-tolerant, distributed web crawler built with Python 3.11+, featuring URL leasing, per-host politeness scheduling, robots.txt compliance, incremental recrawling, distributed deduplication, full-text search, and a live dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      API (FastAPI)                          │
│  POST /search  POST /urls  GET /stats  GET /metrics  /ui   │
└───────────┬─────────────────────────────┬───────────────────┘
            │                             │
            ▼                             ▼
┌───────────────────┐         ┌───────────────────────┐
│   PostgreSQL      │         │    Elasticsearch       │
│  (urls + pages)   │         │  (full-text search)    │
└───────────────────┘         └───────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Redis Streams                            │
│              (distributed work queue)                       │
└───────────┬─────────────────────────────┬───────────────────┘
            │                             │
            ▼                             ▼
┌───────────────────┐         ┌───────────────────────┐
│   Worker 1        │         │    Worker 2            │
│  (consumer)       │         │  (consumer)            │
└───────────────────┘         └───────────────────────┘
```

## Features

### Phase 1 — Foundation
- **URL Normalizer**: Fragment stripping, tracking parameter removal, host lowercasing, trailing slash normalization
- **Async Downloader**: aiohttp-based with retries and exponential backoff
- **HTML Parser**: BeautifulSoup with title extraction, canonical URLs, and relative link resolution
- **PostgreSQL Metadata**: Async SQLAlchemy models for URLs (status tracking) and pages (content metadata)
- **Filesystem Storage**: Raw HTML saved to disk with date-based directory structure

### Phase 2 — Frontier & Politeness
- **robots.txt Compliance**: Fetcher/parser with Redis cache and crawl-delay extraction
- **Per-Host Scheduler**: Enforces politeness with configurable crawl delays per domain
- **URL Leasing**: TTL-based leasing for fault tolerance — if a worker crashes, URLs auto-return to the queue
- **Priority Queue**: Redis sorted set with configurable priorities
- **Bloom Filter + Redis SET**: Dual-layer deduplication for fast pre-checks

### Phase 3 — Distributed Workers
- **Redis Streams**: Consumer groups for distributed work distribution across multiple workers
- **Graceful Shutdown**: SIGINT/SIGTERM handling with in-progress work completion
- **Simhash Dedup**: Content fingerprinting with Hamming distance threshold for near-duplicate detection

### Phase 4 — Search & API
- **Elasticsearch**: Full-text search with title weighting (^3) and body content
- **FastAPI Endpoints**:
  - `POST /search` — Full-text search across indexed pages
  - `POST /urls` — Enqueue new URLs for crawling
  - `GET /stats` — Crawler statistics
  - `GET /health` — Service health checks (API, Redis, Elasticsearch)
  - `GET /metrics` — Live metrics from PostgreSQL
- **ETag Recrawling**: Conditional requests to avoid re-downloading unchanged pages

### Phase 5 — Production Polish
- **Prometheus Metrics**: Counters, gauges, and histograms for monitoring
- **Structured Logging**: JSON-formatted logs with request context
- **Docker Compose**: Full stack deployment (PostgreSQL, Redis, Elasticsearch, API, Workers)
- **Live Dashboard**: Real-time UI showing crawl stats, search, URL enqueueing, and health checks

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Git

### 1. Clone & Start

```bash
git clone <repo-url>
cd web-crawler
docker compose up -d
```

This starts:
- **PostgreSQL** on port 5432
- **Redis** on port 6379
- **Elasticsearch** on port 9200
- **API** on port 8000
- **Worker 1** and **Worker 2** (consumers)

### 2. Seed a Crawl

```bash
# Install dependencies locally (for the seed script)
pip install -e .

# Seed a URL to start crawling
python -m scripts.seed https://example.com
```

Or use the API:
```bash
curl -X POST http://localhost:8000/urls \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
```

### 3. Access the Dashboard

Open [http://localhost:8000/ui](http://localhost:8000/ui) in your browser.

### 4. Search

```bash
# Via API
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "your search term"}'
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/search` | Full-text search across indexed pages |
| `POST` | `/urls` | Enqueue URLs for crawling |
| `GET` | `/stats` | Crawler configuration and stats |
| `GET` | `/metrics` | Live crawl metrics from database |
| `GET` | `/health` | Health checks for all services |
| `GET` | `/ui` | Dashboard UI |
| `GET` | `/pages/{url}` | Get specific page details |

## Configuration

All settings are configured via environment variables (with defaults in `src/config.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `ELASTICSEARCH_URL` | `http://localhost:9200` | Elasticsearch URL |
| `CRAWL_DELAY_DEFAULT` | `1.0` | Default delay between requests (seconds) |
| `MAX_CONCURRENT_REQUESTS` | `20` | Max concurrent downloads per worker |
| `MAX_DEPTH` | `5` | Maximum crawl depth |
| `LEASE_TTL` | `300` | URL lease TTL in seconds |
| `BLOOM_FILTER_SIZE` | `1000000` | Bloom filter capacity |

## Project Structure

```
src/
├── api/
│   ├── models.py          # Pydantic request/response models
│   └── routes.py          # FastAPI endpoints
├── crawler/
│   ├── downloader.py      # Async HTTP downloader
│   ├── parser.py          # HTML parser and link extractor
│   ├── robots.py          # robots.txt parser with Redis cache
│   └── simhash.py         # Content fingerprinting for dedup
├── frontier/
│   ├── dedup.py           # Bloom filter + Redis SET dedup
│   ├── lease.py           # URL leasing with TTL
│   ├── normalizer.py      # URL normalization
│   ├── priority_queue.py  # Redis sorted set queue
│   ├── scheduler.py       # Per-host politeness scheduler
│   └── stream_queue.py    # Redis Streams consumer groups
├── models/
│   └── db.py              # SQLAlchemy async models
├── storage/
│   ├── html_store.py      # Filesystem HTML storage
│   ├── metadata.py        # PostgreSQL CRUD operations
│   └── search_index.py    # Elasticsearch search index
├── static/
│   └── index.html         # Dashboard UI
├── config.py              # Pydantic-settings configuration
├── logging_config.py      # Structured JSON logging
├── main.py                # FastAPI app entry point
├── metrics.py             # Prometheus metrics
└── worker_app.py          # Worker process with consumer loop
tests/
├── test_normalizer.py     # URL normalizer tests (16)
├── test_parser.py         # HTML parser tests (6)
├── test_phase2.py         # Frontier + politeness tests (12)
├── test_simhash.py        # Simhash tests (7)
└── test_stream.py         # Redis Streams tests (4)
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| HTTP Server | FastAPI + Uvicorn |
| Database | PostgreSQL 16 (asyncpg) |
| Cache/Queue | Redis 7 (redis-py) |
| Search | Elasticsearch 8.15 |
| HTTP Client | aiohttp |
| HTML Parser | BeautifulSoup4 + lxml |
| ORM | SQLAlchemy 2.0 (async) |
| Config | pydantic-settings |
| Metrics | prometheus-client |
| Containerization | Docker + Docker Compose |

## Development

### Run Tests

```bash
python -m pytest -v
```

### Lint

```bash
python -m ruff check src/ tests/
```

### Local Development (without Docker)

```bash
# Start dependencies
docker compose up -d postgres redis elasticsearch

# Run API
python -m uvicorn src.main:app --reload

# Run Worker
python -m src.worker_app
```

## License

MIT
