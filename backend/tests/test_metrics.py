import metrics


class TestCounters:
    def test_increments_from_zero(self):
        metrics.incr("queries_total")
        assert metrics.snapshot()["counters"]["queries_total"] == 1

    def test_accumulates(self):
        for _ in range(5):
            metrics.incr("queries_total")
        assert metrics.snapshot()["counters"]["queries_total"] == 5

    def test_custom_amount(self):
        metrics.incr("errors", 3)
        assert metrics.snapshot()["counters"]["errors"] == 3

    def test_unknown_counter_is_absent(self):
        assert "never_touched" not in metrics.snapshot()["counters"]


class TestCacheHitRate:
    def test_zero_when_no_queries(self):
        assert metrics.snapshot()["cache_hit_rate"] == 0.0

    def test_computed_against_total_queries(self):
        for _ in range(4):
            metrics.incr("queries_total")
        metrics.incr("cache_hits")
        assert metrics.snapshot()["cache_hit_rate"] == 0.25


class TestLatency:
    def test_empty_when_nothing_observed(self):
        assert metrics.snapshot()["latency_ms"] == {"count": 0, "p50": 0, "p95": 0, "max": 0}

    def test_tracks_count_and_max(self):
        for ms in (100, 200, 300):
            metrics.observe_latency(ms)
        latency = metrics.snapshot()["latency_ms"]
        assert latency["count"] == 3
        assert latency["max"] == 300

    def test_percentiles_are_ordered(self):
        for ms in range(1, 101):
            metrics.observe_latency(ms)
        latency = metrics.snapshot()["latency_ms"]
        assert latency["p50"] <= latency["p95"] <= latency["max"]

    def test_p50_is_the_middle(self):
        for ms in range(1, 101):
            metrics.observe_latency(ms)
        assert 45 <= metrics.snapshot()["latency_ms"]["p50"] <= 55

    def test_sample_buffer_is_bounded(self):
        for ms in range(2000):
            metrics.observe_latency(ms)
        assert metrics.snapshot()["latency_ms"]["count"] == 1000


class TestReset:
    def test_clears_everything(self):
        metrics.incr("queries_total")
        metrics.observe_latency(50)
        metrics.reset()
        snap = metrics.snapshot()
        assert snap["counters"] == {}
        assert snap["latency_ms"]["count"] == 0
