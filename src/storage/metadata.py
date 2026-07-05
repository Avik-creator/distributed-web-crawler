import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import select, update

from src.models.db import Page, Url, UrlStatus, async_session
from src.storage.html_store import HtmlStore

logger = logging.getLogger(__name__)


class MetadataStore:
    def __init__(self) -> None:
        self.html_store = HtmlStore()

    async def url_exists(self, normalized_url: str) -> bool:
        url_hash = hashlib.sha256(normalized_url.encode()).hexdigest()
        async with async_session() as session:
            result = await session.execute(
                select(Url.id).where(Url.hash == url_hash)
            )
            return result.scalar_one_or_none() is not None

    async def add_url(
        self,
        url: str,
        normalized_url: str,
        host: str,
        priority: int = 50,
        depth: int = 0,
    ) -> int | None:
        url_hash = hashlib.sha256(normalized_url.encode()).hexdigest()

        if await self.url_exists(normalized_url):
            return None

        async with async_session() as session:
            db_url = Url(
                url=url,
                normalized_url=normalized_url,
                host=host,
                hash=url_hash,
                status=UrlStatus.PENDING,
                priority=priority,
                depth=depth,
            )
            session.add(db_url)
            await session.commit()
            await session.refresh(db_url)
            logger.info("Added URL: %s (id=%d)", normalized_url, db_url.id)
            return db_url.id

    async def mark_crawling(self, url_id: int) -> None:
        async with async_session() as session:
            await session.execute(
                update(Url).where(Url.id == url_id).values(status=UrlStatus.CRAWLING)
            )
            await session.commit()

    async def mark_crawled(self, url_id: int) -> None:
        async with async_session() as session:
            await session.execute(
                update(Url)
                .where(Url.id == url_id)
                .values(
                    status=UrlStatus.CRAWLED,
                    last_crawled=datetime.now(UTC),
                )
            )
            await session.commit()

    async def mark_failed(self, url_id: int) -> None:
        async with async_session() as session:
            await session.execute(
                update(Url).where(Url.id == url_id).values(status=UrlStatus.FAILED)
            )
            await session.commit()

    async def store_page(
        self,
        url_id: int,
        html: str,
        title: str,
        status_code: int,
        etag: str | None = None,
    ) -> int:
        html_path = self.html_store.store(
            normalized_url=f"url_{url_id}", html=html
        )
        content_hash = hashlib.sha256(html.encode()).hexdigest()

        async with async_session() as session:
            page = Page(
                url_id=url_id,
                title=title,
                html_path=html_path,
                status_code=status_code,
                etag=etag,
                content_hash=content_hash,
                size=len(html.encode()),
            )
            session.add(page)
            await session.commit()
            await session.refresh(page)
            return page.id

    async def get_pending_urls(self, limit: int = 10) -> list[Url]:
        async with async_session() as session:
            result = await session.execute(
                select(Url)
                .where(Url.status == UrlStatus.PENDING)
                .order_by(Url.priority.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
