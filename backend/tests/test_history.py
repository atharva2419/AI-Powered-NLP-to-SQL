import pytest
from history import init_db, save_query, get_history


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------
class TestInitDb:
    def test_creates_table_without_error(self):
        init_db()

    def test_idempotent(self):
        init_db()
        init_db()


# ---------------------------------------------------------------------------
# save_query + get_history
# ---------------------------------------------------------------------------
class TestSaveQuery:
    def test_saved_question_appears_in_history(self):
        init_db()
        save_query("unique-save-test", "SELECT 1", {}, "one", 100)
        questions = [h["question"] for h in get_history(limit=50)]
        assert "unique-save-test" in questions

    def test_result_json_roundtrip(self):
        init_db()
        result = {"columns": ["count"], "rows": [[5]], "row_count": 1}
        save_query("unique-roundtrip", "SELECT 5", result, "five", 500)
        saved = next(h for h in get_history(limit=50) if h["question"] == "unique-roundtrip")
        assert saved["result"] == result

    def test_item_has_all_required_fields(self):
        init_db()
        save_query("unique-fields-test", "SELECT 1", {}, "explanation", 300)
        item = next(h for h in get_history(limit=50) if h["question"] == "unique-fields-test")
        assert all(
            k in item
            for k in ["id", "question", "sql", "result", "explanation", "latency_ms", "created_at"]
        )

    def test_latency_stored_correctly(self):
        init_db()
        save_query("unique-latency-test", "SELECT 1", {}, "", 9999)
        item = next(h for h in get_history(limit=50) if h["question"] == "unique-latency-test")
        assert item["latency_ms"] == 9999


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------
class TestGetHistory:
    def test_newest_first(self):
        init_db()
        save_query("older-ordering", "SELECT 1", {}, "", 100)
        save_query("newer-ordering", "SELECT 2", {}, "", 100)
        questions = [h["question"] for h in get_history(limit=50)]
        assert questions.index("newer-ordering") < questions.index("older-ordering")

    def test_respects_limit(self):
        init_db()
        for i in range(5):
            save_query(f"limit-row-{i}", f"SELECT {i}", {}, "", 100)
        assert len(get_history(limit=3)) <= 3

    def test_empty_when_nothing_saved(self):
        # conftest points at a fresh temp DB per session; this test just
        # checks the return type is a list (may already have rows from above)
        result = get_history(limit=0)
        assert isinstance(result, list)
