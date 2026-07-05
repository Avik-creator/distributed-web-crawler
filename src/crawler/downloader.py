import asyncio
import logging
from dataclasses import dataclass

import aiohttp

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    url: str
    status_code: int
    html: str
    etag: str | None = None
    content_type: str | None = None


class DownloadError(Exception):
    def __init__(self, url: str, status_code: int | None = None, message: str = ""):
        self.url = url
        self.status_code = status_code
        super().__init__(f"Failed to download {url}: {message}")


class Downloader:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=settings.request_timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": settings.user_agent},
            )
        return self._session

    async def download(
        self,
        url: str,
        etag: str | None = None,
    ) -> DownloadResult:
        session = await self._get_session()
        headers = {}
        if etag:
            headers["If-None-Match"] = etag

        last_exc: Exception | None = None
        for attempt in range(1, settings.retry_count + 1):
            try:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    if resp.status == 304:
                        raise DownloadError(url, 304, "Not Modified")

                    if resp.status >= 400:
                        raise DownloadError(url, resp.status, f"HTTP {resp.status}")

                    html = await resp.text()
                    return DownloadResult(
                        url=str(resp.url),
                        status_code=resp.status,
                        html=html,
                        etag=resp.headers.get("ETag"),
                        content_type=resp.headers.get("Content-Type"),
                    )

            except (TimeoutError, aiohttp.ClientError) as exc:
                last_exc = exc
                if attempt < settings.retry_count:
                    delay = settings.retry_backoff_factor ** attempt
                    logger.warning(
                        "Attempt %d for %s failed: %s. Retrying in %.1fs",
                        attempt,
                        url,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)

        raise DownloadError(url, message=str(last_exc))

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
