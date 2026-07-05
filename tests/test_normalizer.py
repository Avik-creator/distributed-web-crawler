

from src.frontier.normalizer import extract_host, normalize_url, url_hash


class TestNormalizeUrl:
    def test_strips_fragment(self) -> None:
        result = normalize_url("https://example.com/page#section")
        assert result == "https://example.com/page"

    def test_strips_tracking_params(self) -> None:
        result = normalize_url("https://example.com/page?utm_source=abc&utm_medium=def&id=1")
        assert result == "https://example.com/page?id=1"

    def test_lowercases_host(self) -> None:
        result = normalize_url("https://EXAMPLE.COM/Page")
        assert result == "https://example.com/Page"

    def test_trailing_slash(self) -> None:
        result = normalize_url("https://example.com/")
        assert result == "https://example.com/"

    def test_adds_slash_for_empty_path(self) -> None:
        result = normalize_url("https://example.com")
        assert result == "https://example.com/"

    def test_strips_duplicate_slashes(self) -> None:
        result = normalize_url("https://example.com//page//sub")
        assert result == "https://example.com/page/sub"

    def test_rejects_non_http(self) -> None:
        assert normalize_url("ftp://example.com") is None

    def test_rejects_no_netloc(self) -> None:
        assert normalize_url("/relative/path") is None

    def test_relative_url_with_base(self) -> None:
        result = normalize_url("/about", base_url="https://example.com/page")
        assert result == "https://example.com/about"

    def test_full_url_ignores_base(self) -> None:
        result = normalize_url("https://other.com/page", base_url="https://example.com/")
        assert result == "https://other.com/page"

    def test_query_params_preserved_except_tracking(self) -> None:
        result = normalize_url("https://example.com/search?q=python&page=2")
        assert result == "https://example.com/search?q=python&page=2"


class TestUrlHash:
    def test_deterministic(self) -> None:
        h1 = url_hash("https://example.com/page")
        h2 = url_hash("https://example.com/page")
        assert h1 == h2

    def test_different_urls_different_hashes(self) -> None:
        h1 = url_hash("https://example.com/page1")
        h2 = url_hash("https://example.com/page2")
        assert h1 != h2

    def test_hash_length(self) -> None:
        h = url_hash("https://example.com")
        assert len(h) == 64


class TestExtractHost:
    def test_simple_host(self) -> None:
        assert extract_host("https://example.com/page") == "example.com"

    def test_subdomain(self) -> None:
        assert extract_host("https://blog.example.com/post") == "blog.example.com"
