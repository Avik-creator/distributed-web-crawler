from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://crawler:crawler@localhost:5432/crawler"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "crawler_pages"

    # Crawler
    max_depth: int = 5
    max_concurrent_requests: int = 20
    request_timeout: int = 15
    retry_count: int = 2
    retry_backoff_factor: float = 1.0
    crawl_delay_default: float = 0.5
    user_agent: str = "WebCrawler/0.1 (+https://github.com/example/web-crawler)"

    # Storage
    html_storage_path: Path = Path("html_storage")

    # Frontier
    lease_ttl_seconds: int = 300
    robots_cache_ttl: int = 3600

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = {"env_prefix": "CRAWLER_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
