import hashlib
from pathlib import Path

from src.config import settings


class HtmlStore:
    def __init__(self) -> None:
        self.base_path = settings.html_storage_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def store(self, url: str, html: str) -> str:
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        file_path = self.base_path / f"{url_hash}.html"
        file_path.write_text(html, encoding="utf-8")
        return str(file_path)

    def load(self, file_path: str) -> str:
        return Path(file_path).read_text(encoding="utf-8")
