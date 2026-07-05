from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://crawler:crawler@localhost:5432/crawler"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Crawler
    max_depth: int = 5
    max_concurrent_requests: int = 10
    request_timeout: int = 30
    retry_count: int = 3
    retry_backoff_factor: float = 1.5
    crawl_delay_default: float = 1.0
    user_agent: str = "WebCrawler/0.1 (+https://github.com/example/web-crawler)"

    # Storage
    html_storage_path: Path = Path("html_storage")

    # Frontier
    lease_ttl_seconds: int = 300
    robots_cache_ttl: int = 3600

    model_config = {"env_prefix": "CRAWLER_", "env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
