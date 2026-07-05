import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class UrlStatus(enum.StrEnum):
    PENDING = "pending"
    CRAWLING = "crawling"
    CRAWLED = "crawled"
    FAILED = "failed"
    ROBOTS_BLOCKED = "robots_blocked"


class Url(Base):
    __tablename__ = "urls"
    __table_args__ = (
        Index("ix_urls_host_next_crawl", "host", "next_crawl"),
        Index("ix_urls_hash", "hash", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[UrlStatus] = mapped_column(
        Enum(UrlStatus), default=UrlStatus.PENDING, nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, default=50)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    last_crawled: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_crawl: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
