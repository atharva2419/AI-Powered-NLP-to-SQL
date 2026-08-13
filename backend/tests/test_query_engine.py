from unittest.mock import MagicMock, patch

import pytest

import config
import query_engine
from query_engine import run_pipeline, run_query, translate_to_sql
from sql_guard import SQLGuardError


def _mock_completion(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    return resp


# ---------------------------------------------------------------------------
# run_query
# ---------------------------------------------------------------------------
class TestRunQuery:
    def test_count_all_rows(self):
        result = run_query("SELECT COUNT(*) AS cnt FROM taxi")
        assert result["columns"] == ["cnt"]
        assert result["rows"][0][0] == 5
        assert result["row_count"] == 1

    def test_average_fare(self):
        result = run_query("SELECT AVG(fare_amount) AS avg_fare FROM taxi")
        assert abs(result["rows"][0][0] - 14.2) < 0.01

    def test_filter_by_payment_type(self):
        # payment_type=1 appears in rows 0, 2, 4 → 3 trips
        result = run_query("SELECT COUNT(*) AS cnt FROM taxi WHERE payment_type = 1")
        assert result["rows"][0][0] == 3

    def test_returns_columns_list(self):
        result = run_query("SELECT VendorID, fare_amount FROM taxi LIMIT 2")
        assert result["columns"] == ["VendorID", "fare_amount"]
        assert result["row_count"] == 2

    def test_invalid_sql_returns_error_dict(self):
        result = run_query("SELECT nonexistent_col FROM taxi")
        assert "error" in result
        assert "columns" not in result

    def test_timestamps_are_json_safe(self):
        result = run_query("SELECT tpep_pickup_datetime FROM taxi LIMIT 1")
        assert isinstance(result["rows"][0][0], str)

    def test_tolerates_trailing_semicolon(self):
        assert run_query("SELECT 1 AS one FROM taxi LIMIT 1;")["row_count"] == 1

    def test_row_cap_is_pushed_into_sql(self):
        """The cap must reach the database, not be applied after fetching.

        Fetching everything and truncating afterwards is what the original
        code did, which meant `SELECT * FROM taxi` materialised all 41M rows
        into pandas before keeping 100.
        """
        with patch.object(config, "MAX_RESULT_ROWS", 2), \
             patch("query_engine.sql_guard.enforce_limit",
                   wraps=query_engine.sql_guard.enforce_limit) as limiter:
            result = run_query("SELECT * FROM taxi")

        limiter.assert_called_once()
        assert limiter.call_args[0][1] == 2  # cap handed to the SQL wrapper
        assert result["row_count"] == 2
        assert result["truncated"] is True

    def test_not_truncated_when_under_the_cap(self):
        result = run_query("SELECT * FROM taxi")
        assert result["row_count"] == 5
        assert result["truncated"] is False

    def test_query_is_armed_with_a_timeout_watchdog(self):
        with patch.object(config, "QUERY_TIMEOUT_SECONDS", 7), \
             patch("query_engine.threading.Timer") as timer:
            run_query("SELECT 1 AS a FROM taxi LIMIT 1")

        assert timer.call_args[0][0] == 7
        timer.return_value.start.assert_called_once()
        timer.return_value.cancel.assert_called_once()  # always disarmed

    def test_interrupted_query_reports_a_timeout(self):
        """When the watchdog fires, DuckDB raises InterruptException.

        Surfaced as a plain "hit the time limit" message rather than the raw
        exception, which says only "INTERRUPT Error: Interrupted!".
        """
        fake_con = MagicMock()
        fake_con.cursor.return_value.execute.side_effect = query_engine.duckdb.InterruptException(
            "Interrupted!"
        )
        with patch.object(query_engine, "_con", fake_con), \
             patch.object(config, "QUERY_TIMEOUT_SECONDS", 30):
            result = run_query("SELECT 1 FROM taxi")

        assert result["error"] == "Query exceeded the 30s time limit."


# ---------------------------------------------------------------------------
# translate_to_sql
# ---------------------------------------------------------------------------
class TestTranslateToSQL:
    def test_returns_stripped_sql(self):
        with patch.object(
            query_engine._client.chat.completions,
            "create",
            return_value=_mock_completion("  SELECT COUNT(*) FROM taxi  \n"),
        ):
            assert translate_to_sql("How many trips?", "VendorID INTEGER") == (
                "SELECT COUNT(*) FROM taxi"
            )

    def test_passes_schema_and_question(self):
        with patch.object(
            query_engine._client.chat.completions, "create",
            return_value=_mock_completion("SELECT 1"),
        ) as create:
            translate_to_sql("test question", "VendorID INTEGER, fare_amount DOUBLE")
        messages = create.call_args[1]["messages"]
        assert "VendorID INTEGER, fare_amount DOUBLE" in messages[0]["content"]
        assert messages[-1]["content"] == "test question"

    def test_prompt_encodes_payment_type_codes(self):
        """Domain knowledge in the prompt is what fixes payment_type questions."""
        with patch.object(
            query_engine._client.chat.completions, "create",
            return_value=_mock_completion("SELECT 1"),
        ) as create:
            translate_to_sql("q", "schema")
        system = create.call_args[1]["messages"][0]["content"]
        assert "1=credit card" in system and "2=cash" in system

    def test_correction_turn_includes_previous_sql_and_error(self):
        with patch.object(
            query_engine._client.chat.completions, "create",
            return_value=_mock_completion("SELECT 2"),
        ) as create:
            translate_to_sql("q", "schema", previous_sql="SELECT bad", error="no such column")
        contents = [m["content"] for m in create.call_args[1]["messages"]]
        assert "SELECT bad" in contents
        assert any("no such column" in c for c in contents)

    def test_uses_deterministic_temperature(self):
        with patch.object(
            query_engine._client.chat.completions, "create",
            return_value=_mock_completion("SELECT 1"),
        ) as create:
            translate_to_sql("q", "schema")
        assert create.call_args[1]["temperature"] == config.LLM_TEMPERATURE


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------
class TestRunPipeline:
    def test_successful_pipeline(self):
        with patch("query_engine.translate_to_sql", return_value="SELECT COUNT(*) AS cnt FROM taxi"), \
             patch("query_engine.explain_result", return_value="There were 5 trips."):
            result = run_pipeline("How many trips?")

        assert result["sql"] == "SELECT COUNT(*) AS cnt FROM taxi"
        assert result["explanation"] == "There were 5 trips."
        assert result["result"]["row_count"] == 1
        assert result["attempts"] == 1

    def test_strips_markdown_the_model_wraps_sql_in(self):
        with patch("query_engine.translate_to_sql",
                   return_value="```sql\nSELECT COUNT(*) AS cnt FROM taxi;\n```"), \
             patch("query_engine.explain_result", return_value="ok"):
            result = run_pipeline("How many trips?")
        assert result["sql"] == "SELECT COUNT(*) AS cnt FROM taxi"

    def test_explain_can_be_skipped(self):
        with patch("query_engine.translate_to_sql", return_value="SELECT 1 AS a FROM taxi"), \
             patch("query_engine.explain_result") as explain:
            result = run_pipeline("q", explain=False)
        explain.assert_not_called()
        assert result["explanation"] == ""

    def test_blocks_dangerous_sql_from_llm(self):
        with patch("query_engine.translate_to_sql", return_value="DROP TABLE taxi"):
            with pytest.raises(SQLGuardError, match="DROP"):
                run_pipeline("delete all data")


class TestSelfCorrection:
    def test_retries_with_the_database_error_and_recovers(self):
        attempts = ["SELECT nonexistent_col FROM taxi", "SELECT COUNT(*) AS cnt FROM taxi"]
        with patch("query_engine.translate_to_sql", side_effect=attempts) as translate, \
             patch("query_engine.explain_result", return_value="ok"):
            result = run_pipeline("How many trips?")

        assert result["attempts"] == 2
        assert result["result"]["row_count"] == 1
        # The second call must have been told what went wrong.
        _, kwargs = translate.call_args
        second_call_args = translate.call_args[0]
        assert "nonexistent_col" in second_call_args[2]
        assert second_call_args[3]

    def test_retries_after_a_guard_rejection(self):
        attempts = ["DROP TABLE taxi", "SELECT COUNT(*) AS cnt FROM taxi"]
        with patch("query_engine.translate_to_sql", side_effect=attempts), \
             patch("query_engine.explain_result", return_value="ok"):
            result = run_pipeline("How many trips?")
        assert result["attempts"] == 2
        assert "error" not in result["result"]

    def test_gives_up_after_max_retries(self):
        with patch.object(config, "MAX_SQL_RETRIES", 1), \
             patch("query_engine.translate_to_sql", return_value="SELECT bad_col FROM taxi") as translate, \
             patch("query_engine.explain_result") as explain:
            result = run_pipeline("nonsense")

        assert translate.call_count == 2  # 1 initial + 1 retry
        explain.assert_not_called()
        assert "error" in result["result"]
        assert result["explanation"] == ""

    def test_returns_the_failed_sql_so_the_user_sees_something_real(self):
        with patch.object(config, "MAX_SQL_RETRIES", 0), \
             patch("query_engine.translate_to_sql", return_value="SELECT bad_col FROM taxi"):
            result = run_pipeline("nonsense")
        assert result["sql"] == "SELECT bad_col FROM taxi"

    def test_raises_when_every_attempt_is_unsafe(self):
        with patch.object(config, "MAX_SQL_RETRIES", 1), \
             patch("query_engine.translate_to_sql", return_value="DELETE FROM taxi"):
            with pytest.raises(SQLGuardError):
                run_pipeline("wipe it")
