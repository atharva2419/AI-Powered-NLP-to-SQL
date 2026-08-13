import time
from unittest.mock import patch

import cache
import config

PAYLOAD = {
    "sql": "SELECT COUNT(*) FROM taxi",
    "result": {"columns": ["c"], "rows": [[5]], "row_count": 1},
    "explanation": "Five trips.",
    "attempts": 1,
}


class TestKeyNormalization:
    def test_identical_questions_share_a_key(self):
        assert cache.make_key("How many trips?") == cache.make_key("How many trips?")

    def test_case_is_insignificant(self):
        assert cache.make_key("How Many Trips?") == cache.make_key("how many trips?")

    def test_whitespace_is_insignificant(self):
        assert cache.make_key("  how   many trips? ") == cache.make_key("how many trips?")

    def test_trailing_question_mark_is_insignificant(self):
        assert cache.make_key("how many trips") == cache.make_key("how many trips?")

    def test_different_questions_differ(self):
        assert cache.make_key("how many trips") != cache.make_key("average fare")

    def test_model_is_part_of_the_key(self):
        baseline = cache.make_key("how many trips")
        with patch.object(config, "MODEL_NAME", "some-other-model"):
            assert cache.make_key("how many trips") != baseline


class TestGetPut:
    def test_miss_returns_none(self):
        assert cache.get("never asked before") is None

    def test_round_trip(self):
        cache.put("How many trips?", PAYLOAD)
        assert cache.get("How many trips?") == PAYLOAD

    def test_hit_survives_question_reformatting(self):
        cache.put("How many trips?", PAYLOAD)
        assert cache.get("  how many TRIPS ") == PAYLOAD

    def test_put_overwrites(self):
        cache.put("q", PAYLOAD)
        cache.put("q", {**PAYLOAD, "explanation": "updated"})
        assert cache.get("q")["explanation"] == "updated"

    def test_clear_empties_the_cache(self):
        cache.put("q", PAYLOAD)
        cache.clear()
        assert cache.get("q") is None

    def test_expired_entry_is_a_miss(self):
        cache.put("q", PAYLOAD)
        with patch("cache.time.time", return_value=time.time() + config.CACHE_TTL_SECONDS + 1):
            assert cache.get("q") is None

    def test_disabled_cache_never_hits(self):
        cache.put("q", PAYLOAD)
        with patch.object(config, "CACHE_ENABLED", False):
            assert cache.get("q") is None


class TestStats:
    def test_counts_entries(self):
        cache.put("a", PAYLOAD)
        cache.put("b", PAYLOAD)
        assert cache.stats()["entries"] == 2

    def test_counts_hits(self):
        cache.put("a", PAYLOAD)
        cache.get("a")
        cache.get("a")
        assert cache.stats()["cumulative_hits"] == 2

    def test_stats_on_empty_cache(self):
        assert cache.stats() == {"entries": 0, "cumulative_hits": 0}
