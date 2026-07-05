from src.crawler.simhash import hamming_distance, is_near_duplicate, simhash


class TestSimhash:
    def test_identical_text(self) -> None:
        h1 = simhash("hello world test")
        h2 = simhash("hello world test")
        assert h1 == h2
        assert hamming_distance(h1, h2) == 0

    def test_similar_text(self) -> None:
        h1 = simhash("the quick brown fox jumps over the lazy dog")
        h2 = simhash("the quick brown fox jumps over the lazy dogs")
        assert hamming_distance(h1, h2) <= 5

    def test_different_text(self) -> None:
        h1 = simhash("the quick brown fox")
        h2 = simhash("python programming language tutorial")
        assert hamming_distance(h1, h2) > 10

    def test_empty_text(self) -> None:
        h = simhash("")
        assert h == 0

    def test_near_duplicate_detection(self) -> None:
        base = "web crawling is the process of downloading web pages from the internet. " * 10
        h1 = simhash(base)
        h2 = simhash(base.replace("downloading", "fetching"))
        assert is_near_duplicate(h1, h2, threshold=10) is True

    def test_not_near_duplicate(self) -> None:
        h1 = simhash("web crawling is the process of downloading web pages")
        h2 = simhash("machine learning algorithms for natural language processing")
        assert is_near_duplicate(h1, h2, threshold=3) is False

    def test_html_content(self) -> None:
        html1 = "<html><head><title>Test</title></head><body>Hello world</body></html>"
        html2 = "<html><head><title>Test</title></head><body>Hello world!</body></html>"
        h1 = simhash(html1)
        h2 = simhash(html2)
        assert hamming_distance(h1, h2) <= 5
