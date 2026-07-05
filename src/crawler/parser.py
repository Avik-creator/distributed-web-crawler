
from bs4 import BeautifulSoup

from src.frontier.normalizer import normalize_url


def parse_html(html: str, base_url: str) -> tuple[str, list[str]]:
    soup = BeautifulSoup(html, "lxml")

    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    links: list[str] = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        normalized = normalize_url(href, base_url=base_url)
        if normalized:
            links.append(normalized)

    return title, links
