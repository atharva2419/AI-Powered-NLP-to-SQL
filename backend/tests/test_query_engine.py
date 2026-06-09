import pytest
from unittest.mock import MagicMock, patch

import query_engine
from query_engine import _validate_sql, run_query, run_pipeline, translate_to_sql


# ---------------------------------------------------------------------------
# _validate_sql
# ---------------------------------------------------------------------------
class TestValidateSQL:
    def test_valid_select(self):
        _validate_sql("SELECT COUNT(*) FROM taxi")

    def test_valid_complex_select(self):
        _validate_sql(
            "SELECT AVG(fare_amount), COUNT(*) FROM taxi WHERE payment_type = 1 GROUP BY VendorID"
        )

    @pytest.mark.parametrize("keyword", ["DROP", "DELETE", "INSERT", "UPDATE", "CREATE", "ALTER"])
    def test_blocks_each_keyword(self, keyword: str):
        with pytest.raises(ValueError, match=keyword):
            _validate_sql(f"{keyword} TABLE taxi")

    def test_case_insensitive(self):
        with pytest.raises(ValueError, match="DROP"):
            _validate_sql("drop table taxi")

    def test_keyword_inside_longer_word_is_not_blocked(self):
        # "CREATED_AT" contains "CREATE" as a substring but is a column name
        _validate_sql("SELECT created_at FROM taxi")

    def test_error_message_lists_keyword(self):
        with pytest.raises(ValueError, match="Only SELECT queries are permitted"):
            _validate_sql("DROP TABLE taxi")


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
        assert "VendorID" in result["columns"]
        assert "fare_amount" in result["columns"]
        assert result["row_count"] == 2

    def test_invalid_sql_returns_error_dict(self):
        result = run_query("SELECT nonexistent_col FROM taxi")
        assert "error" in result
        assert "columns" not in result

    def test_row_count_capped_at_100(self):
        # Only 5 rows in test data, all returned
        result = run_query("SELECT * FROM taxi")
        assert result["row_count"] == 5


# ---------------------------------------------------------------------------
# translate_to_sql
# ---------------------------------------------------------------------------
class TestTranslateToSQL:
    def test_returns_stripped_sql(self):
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "  SELECT COUNT(*) FROM taxi  \n"

        with patch.object(query_engine._client.chat.completions, "create", return_value=mock_resp):
            result = translate_to_sql("How many trips?", "VendorID INTEGER")

        assert result == "SELECT COUNT(*) FROM taxi"

    def test_passes_schema_in_prompt(self):
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "SELECT 1"

        with patch.object(query_engine._client.chat.completions, "create", return_value=mock_resp) as mock_create:
            translate_to_sql("test question", "VendorID INTEGER, fare_amount DOUBLE")

        call_kwargs = mock_create.call_args
        prompt = call_kwargs[1]["messages"][0]["content"]
        assert "VendorID INTEGER, fare_amount DOUBLE" in prompt
        assert "test question" in prompt


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
        assert "error" not in result["result"]

    def test_blocks_dangerous_sql_from_llm(self):
        with patch("query_engine.translate_to_sql", return_value="DROP TABLE taxi"):
            with pytest.raises(ValueError, match="DROP"):
                run_pipeline("delete all data")

    def test_skips_explanation_when_query_fails(self):
        with patch("query_engine.translate_to_sql", return_value="SELECT bad_col FROM taxi"), \
             patch("query_engine.explain_result") as mock_explain:
            result = run_pipeline("nonsense question")

        mock_explain.assert_not_called()
        assert "error" in result["result"]
        assert result["explanation"] == ""
