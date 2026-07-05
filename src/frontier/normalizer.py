import hashlib
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}

SCHEMES = {"http", "https"}


def normalize_url(raw_url: str, base_url: str | None = None) -> str | None:
    if base_url:
        raw_url = urljoin(base_url, raw_url)

    parsed = urlparse(raw_url)

    if parsed.scheme not in SCHEMES:
        return None

    if not parsed.netloc:
        return None

    host = parsed.hostname or ""
    host = host.lower()

    path = parsed.path or "/"
    path = re.sub(r"/+", "/", path)
    path = path.rstrip("/") or "/"

    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v for k, v in query_params.items() if k.lower() not in TRACKING_PARAMS
    }
    query = urlencode(filtered, doseq=True) if filtered else ""

    normalized = urlunparse(
        (
            "https",
            host,
            path,
            "",
            query,
            "",
        )
    )
    return normalized


def url_hash(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode()).hexdigest()


def extract_host(normalized_url: str) -> str:
    parsed = urlparse(normalized_url)
    return parsed.hostname or ""
