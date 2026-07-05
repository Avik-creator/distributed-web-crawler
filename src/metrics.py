from prometheus_client import Counter, Gauge, Histogram

pages_crawled_total = Counter(
    "crawler_pages_crawled_total",
    "Total pages successfully crawled",
    ["host"],
)

pages_failed_total = Counter(
    "crawler_pages_failed_total",
    "Total pages that failed to crawl",
    ["host", "reason"],
)

queue_size = Gauge(
    "crawler_queue_size",
    "Current number of URLs in the queue",
)

crawl_rate = Gauge(
    "crawler_rate_pages_per_second",
    "Current crawl rate in pages per second",
)

active_workers = Gauge(
    "crawler_active_workers",
    "Number of active workers",
)

fetch_duration = Histogram(
    "crawler_fetch_duration_seconds",
    "Time spent downloading a page",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

robots_cache_hits = Counter(
    "crawler_robots_cache_hits_total",
    "Number of robots.txt cache hits",
)

robots_cache_misses = Counter(
    "crawler_robots_cache_misses_total",
    "Number of robots.txt cache misses",
)

dedup_hits = Counter(
    "crawler_dedup_hits_total",
    "Number of duplicate URLs skipped",
)

indexed_pages_total = Counter(
    "crawler_indexed_pages_total",
    "Total pages indexed into Elasticsearch",
)
