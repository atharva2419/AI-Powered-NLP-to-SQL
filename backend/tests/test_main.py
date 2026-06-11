import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

MOCK_PIPELINE = {
    "sql": "SELECT COUNT(*) FROM taxi",
    "result": {"columns": ["count_star()"], "rows": [[5]], "row_count": 1},
    "explanation": "There were 5 trips in total.",
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

    def test_pipeline_exception_returns_400(self):
        with patch("main.run_pipeline", side_effect=Exception("LLM unavailable")):
            resp = client.post("/api/query", json={"question": "test"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "LLM unavailable"

    def test_result_error_returns_400(self):
        bad_pipeline = {
            "sql": "SELECT bad FROM taxi",
            "result": {"error": "Column not found", "columns": [], "rows": [], "row_count": 0},
            "explanation": "",
        }
        with patch("main.run_pipeline", return_value=bad_pipeline):
            resp = client.post("/api/query", json={"question": "bad question"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "Column not found"

    def test_response_shape(self):
        with patch("main.run_pipeline", return_value=MOCK_PIPELINE):
            resp = client.post("/api/query", json={"question": "How many trips?"})
        data = resp.json()
        assert set(data.keys()) == {"sql", "result", "explanation", "latency_ms"}


# ---------------------------------------------------------------------------
# GET /api/examples
# ---------------------------------------------------------------------------
class TestExamplesEndpoint:
    def test_returns_200(self):
        resp = client.get("/api/examples")
        assert resp.status_code == 200

    def test_returns_exactly_6_examples(self):
        resp = client.get("/api/examples")
        assert len(resp.json()["examples"]) == 6

    def test_all_examples_are_strings(self):
        resp = client.get("/api/examples")
        for ex in resp.json()["examples"]:
            assert isinstance(ex, str) and len(ex) > 0


# ---------------------------------------------------------------------------
# GET /api/schema
# ---------------------------------------------------------------------------
class TestSchemaEndpoint:
    def test_returns_200(self):
        resp = client.get("/api/schema")
        assert resp.status_code == 200

    def test_returns_columns_list(self):
        data = resp = client.get("/api/schema").json()
        assert "columns" in data
        assert len(data["columns"]) > 0

    def test_each_column_has_name_and_type(self):
        cols = client.get("/api/schema").json()["columns"]
        for col in cols:
            assert "name" in col and "type" in col

    def test_known_columns_present(self):
        col_names = [c["name"] for c in client.get("/api/schema").json()["columns"]]
        assert "fare_amount" in col_names
        assert "VendorID" in col_names


# ---------------------------------------------------------------------------
# GET /api/history
# ---------------------------------------------------------------------------
class TestHistoryEndpoint:
    def test_returns_200(self):
        with patch("main.history.get_history", return_value=[]):
            resp = client.get("/api/history")
        assert resp.status_code == 200

    def test_returns_history_key(self):
        with patch("main.history.get_history", return_value=[]):
            resp = client.get("/api/history")
        assert "history" in resp.json()

    def test_empty_history(self):
        with patch("main.history.get_history", return_value=[]):
            resp = client.get("/api/history")
        assert resp.json() == {"history": []}

    def test_returns_history_items(self):
        mock_item = {
            "id": 1,
            "question": "How many trips?",
            "sql": "SELECT COUNT(*) FROM taxi",
            "result": {"columns": ["count"], "rows": [[5]], "row_count": 1},
            "explanation": "5 trips.",
            "latency_ms": 1200,
            "created_at": "2024-01-01T10:00:00Z",
        }
        with patch("main.history.get_history", return_value=[mock_item]):
            resp = client.get("/api/history")
        assert resp.json()["history"] == [mock_item]
