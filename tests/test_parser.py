from src.crawler.parser import parse_html


class TestParseHtml:
    def test_extracts_title(self) -> None:
        html = "<html><head><title>Test Page</title></head><body></body></html>"
        title, links = parse_html(html, "https://example.com")
        assert title == "Test Page"
        assert links == []

    def test_extracts_links(self) -> None:
        html = """
        <html><body>
            <a href="/about">About</a>
            <a href="/contact">Contact</a>
        </body></html>
        """
        title, links = parse_html(html, "https://example.com/page")
        assert title == ""
        assert "https://example.com/about" in links
        assert "https://example.com/contact" in links

    def test_extracts_absolute_links(self) -> None:
        html = '<a href="https://other.com/page">Other</a>'
        _, links = parse_html(html, "https://example.com")
        assert "https://other.com/page" in links

    def test_ignores_non_http_links(self) -> None:
        html = '<a href="mailto:test@example.com">Email</a>'
        _, links = parse_html(html, "https://example.com")
        assert links == []

    def test_extracts_meta_description(self) -> None:
        html = """
        <html><head>
            <title>Page</title>
            <meta name="description" content="A description">
        </head><body></body></html>
        """
        title, links = parse_html(html, "https://example.com")
        assert title == "Page"

    def test_empty_html(self) -> None:
        title, links = parse_html("", "https://example.com")
        assert title == ""
        assert links == []
