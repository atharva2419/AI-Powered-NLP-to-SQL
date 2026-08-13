from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import config
from main import app
from sql_guard import SQLGuardError

client = TestClient(app)

MOCK_PIPELINE = {
    "sql": "SELECT COUNT(*) FROM taxi",
    "result": {"columns": ["count_star()"], "rows": [[5]], "row_count": 1, "truncated": False},
    "explanation": "There were 5 trips in total.",
    "attempts": 1,
}


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------
class TestQueryEndpoint:
    def test_valid_question_returns_200(self):
        with patch("main.run_pipeline", return_value=MOCK_PIPELINE):
            resp = client.post("/api/query", json={"question": "How many trips?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sql"] == MOCK_PIPELINE["sql"]
        assert data["explanation"] == MOCK_PIPELINE["explanation"]
        assert isinstance(data["latency_ms"], int)

    def test_response_shape(self):
        with patch("main.run_pipeline", return_value=MOCK_PIPELINE):
            resp = client.post("/api/query", json={"question": "How many trips?"})
        assert set(resp.json()) == {
            "sql", "result", "explanation", "latency_ms", "attempts", "cached",
        }

    def test_reports_attempt_count(self):
        with patch("main.run_pipeline", return_value={**MOCK_PIPELINE, "attempts": 2}):
            resp = client.post("/api/query", json={"question": "How many trips?"})
        assert resp.json()["attempts"] == 2

    def test_empty_question_returns_400(self):
        resp = client.post("/api/query", json={"question": ""})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_question_too_long_returns_400(self):
        resp = client.post("/api/query", json={"question": "a" * 501})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_missing_question_field_returns_400(self):
        resp = client.post("/api/query", json={})
        assert resp.status_code == 400

    def test_unsafe_sql_returns_400(self):
        with patch("main.run_pipeline", side_effect=SQLGuardError("Only SELECT queries are permitted.")):
            resp = client.post("/api/query", json={"question": "drop everything"})
        assert resp.status_code == 400
        assert "Only SELECT" in resp.json()["error"]

    def test_upstream_failure_returns_502(self):
        """An LLM outage is not the caller's fault — 502, not 400."""
        with patch("main.run_pipeline", side_effect=Exception("LLM unavailable")):
            resp = client.post("/api/query", json={"question": "test"})
        assert resp.status_code == 502
        assert "LLM unavailable" in resp.json()["error"]

    def test_result_error_returns_400(self):
        bad_pipeline = {
            "sql": "SELECT bad FROM taxi",
            "result": {"error": "Column not found"},
            "explanation": "",
            "attempts": 3,
        }
        with patch("main.run_pipeline", return_value=bad_pipeline):
            resp = client.post("/api/query", json={"question": "bad question"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "Column not found"

    def test_request_id_header_is_set(self):
        resp = client.get("/api/examples")
        assert len(resp.headers["x-request-id"]) == 8


class TestCaching:
    def test_second_identical_question_is_served_from_cache(self):
        with patch("main.run_pipeline", return_value=MOCK_PIPELINE) as pipeline:
            first = client.post("/api/query", json={"question": "How many trips?"})
            second = client.post("/api/query", json={"question": "How many trips?"})

        pipeline.assert_called_once()  # the LLM was not called twice
        assert first.json()["cached"] is False
        assert second.json()["cached"] is True
        assert second.json()["sql"] == first.json()["sql"]

    def test_cache_hit_skips_the_history_write(self):
        with patch("main.run_pipeline", return_value=MOCK_PIPELINE), \
             patch("main.history.save_query") as save:
            client.post("/api/query", json={"question": "How many trips?"})
            client.post("/api/query", json={"question": "How many trips?"})
        save.assert_called_once()

    def test_failed_queries_are_not_cached(self):
        failing = {"sql": "SELECT bad FROM taxi", "result": {"error": "boom"},
                   "explanation": "", "attempts": 1}
        with patch("main.run_pipeline", return_value=failing) as pipeline:
            client.post("/api/query", json={"question": "bad"})
            client.post("/api/query", json={"question": "bad"})
        assert pipeline.call_count == 2

    def test_history_failure_does_not_break_the_response(self):
        with patch("main.run_pipeline", return_value=MOCK_PIPELINE), \
             patch("main.history.save_query", side_effect=Exception("disk full")):
            resp = client.post("/api/query", json={"question": "How many trips?"})
        assert resp.status_code == 200


class TestRateLimiting:
    def test_returns_429_with_retry_after(self):
        with patch.object(config, "RATE_LIMIT_ENABLED", True), \
             patch.object(config, "RATE_LIMIT_PER_HOUR", 1), \
             patch("main.run_pipeline", return_value=MOCK_PIPELINE):
            client.post("/api/query", json={"question": "first question"})
            resp = client.post("/api/query", json={"question": "second question"})

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert "error" in resp.json()

    def test_cached_questions_still_answer_when_throttled(self):
        """Rate limiting bounds LLM spend; a cache hit costs nothing.

        So a throttled visitor can still replay any question already answered.
        """
        with patch("main.run_pipeline", return_value=MOCK_PIPELINE):
            client.post("/api/query", json={"question": "How many trips?"})

        with patch.object(config, "RATE_LIMIT_ENABLED", True), \
             patch.object(config, "RATE_LIMIT_PER_HOUR", 0):
            cached = client.post("/api/query", json={"question": "How many trips?"})
            fresh = client.post("/api/query", json={"question": "something new"})

        assert cached.status_code == 200
        assert cached.json()["cached"] is True
        assert fresh.status_code == 429  # an uncached question still costs money


# ---------------------------------------------------------------------------
# GET /api/examples
# ---------------------------------------------------------------------------
class TestExamplesEndpoint:
    def test_returns_200(self):
        assert client.get("/api/examples").status_code == 200

    def test_returns_exactly_6_examples(self):
        assert len(client.get("/api/examples").json()["examples"]) == 6

    def test_all_examples_are_strings(self):
        for ex in client.get("/api/examples").json()["examples"]:
            assert isinstance(ex, str) and len(ex) > 0


# ---------------------------------------------------------------------------
# GET /api/schema
# ---------------------------------------------------------------------------
class TestSchemaEndpoint:
    def test_returns_200(self):
        assert client.get("/api/schema").status_code == 200

    def test_returns_columns_list(self):
        data = client.get("/api/schema").json()
        assert "columns" in data
        assert len(data["columns"]) > 0

    def test_each_column_has_name_and_type(self):
        for col in client.get("/api/schema").json()["columns"]:
            assert "name" in col and "type" in col

    def test_known_columns_present(self):
        names = [c["name"] for c in client.get("/api/schema").json()["columns"]]
        assert "fare_amount" in names
        assert "VendorID" in names


# ---------------------------------------------------------------------------
# GET /api/history
# ---------------------------------------------------------------------------
class TestHistoryEndpoint:
    def test_returns_200(self):
        with patch("main.history.get_history", return_value=[]):
            assert client.get("/api/history").status_code == 200

    def test_empty_history(self):
        with patch("main.history.get_history", return_value=[]):
            assert client.get("/api/history").json() == {"history": []}

    def test_returns_history_items(self):
        item = {
            "id": 1,
            "question": "How many trips?",
            "sql": "SELECT COUNT(*) FROM taxi",
            "result": {"columns": ["count"], "rows": [[5]], "row_count": 1},
            "explanation": "5 trips.",
            "latency_ms": 1200,
            "created_at": "2024-01-01T10:00:00Z",
        }
        with patch("main.history.get_history", return_value=[item]):
            assert client.get("/api/history").json()["history"] == [item]


# ---------------------------------------------------------------------------
# Operational endpoints
# ---------------------------------------------------------------------------
class TestMetricsEndpoint:
    def test_returns_200(self):
        assert client.get("/api/metrics").status_code == 200

    def test_exposes_expected_sections(self):
        body = client.get("/api/metrics").json()
        assert {"counters", "cache_hit_rate", "latency_ms", "cache", "rate_limit"} <= set(body)

    def test_counts_queries_and_cache_hits(self):
        with patch("main.run_pipeline", return_value=MOCK_PIPELINE):
            client.post("/api/query", json={"question": "How many trips?"})
            client.post("/api/query", json={"question": "How many trips?"})

        body = client.get("/api/metrics").json()
        assert body["counters"]["queries_total"] == 2
        assert body["counters"]["cache_hits"] == 1
        assert body["cache_hit_rate"] == 0.5


class TestHealthEndpoint:
    def test_healthy_when_the_view_is_queryable(self):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["columns"] > 0

    def test_unhealthy_when_the_data_is_gone(self):
        broken = MagicMock()
        broken.execute.side_effect = Exception("no such table: taxi")
        with patch("main._con", broken):
            resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "unhealthy"
