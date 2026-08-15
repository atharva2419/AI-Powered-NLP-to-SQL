import pytest

import sql_guard
from sql_guard import SQLGuardError


class TestNormalize:
    def test_strips_markdown_fence(self):
        assert sql_guard.normalize("```sql\nSELECT 1\n```") == "SELECT 1"

    def test_strips_bare_fence(self):
        assert sql_guard.normalize("```\nSELECT 1\n```") == "SELECT 1"

    def test_strips_trailing_semicolon(self):
        assert sql_guard.normalize("SELECT 1;  ") == "SELECT 1"

    def test_leaves_clean_sql_untouched(self):
        assert sql_guard.normalize("SELECT 1") == "SELECT 1"


class TestValidateAccepts:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT COUNT(*) FROM taxi",
            "SELECT AVG(fare_amount) AS f FROM taxi WHERE payment_type = 1 GROUP BY VendorID",
            "WITH t AS (SELECT * FROM taxi) SELECT COUNT(*) FROM t",
            "SELECT * FROM taxi ORDER BY fare_amount DESC LIMIT 10",
            "SELECT created_at FROM (SELECT 1 AS created_at)",
            # 'update' and 'drop' appear only inside a string literal
            "SELECT 'drop table taxi' AS s FROM taxi",
            # The zone lookup is part of the dataset, so it stays readable.
            "SELECT Zone FROM zones LIMIT 3",
            # Real practice queries must survive the tightened identifier scan.
            "SELECT pickup_borough, COUNT(*) AS n FROM taxi GROUP BY 1 ORDER BY n DESC",
            "SELECT HOUR(tpep_pickup_datetime) AS hour, AVG(fare_amount) FROM taxi GROUP BY hour",
            "SELECT * FROM taxi WHERE dropoff_zone LIKE 'Midtown%' LIMIT 5",
            "SELECT payment_type, ROUND(AVG(tip_amount), 2) FROM taxi GROUP BY payment_type",
        ],
    )
    def test_accepts_read_only_selects(self, sql: str):
        assert sql_guard.validate(sql)


class TestValidateRejects:
    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE taxi",
            "DELETE FROM taxi",
            "INSERT INTO taxi VALUES (1)",
            "UPDATE taxi SET fare_amount = 0",
            "CREATE TABLE t AS SELECT 1",
            "ALTER TABLE taxi RENAME TO t",
        ],
    )
    def test_rejects_write_statements(self, sql: str):
        with pytest.raises(SQLGuardError, match="Only SELECT"):
            sql_guard.validate(sql)

    def test_rejects_stacked_statements(self):
        # The original keyword denylist could be walked past with a comment;
        # the parser counts statements instead.
        with pytest.raises(SQLGuardError, match="single statement"):
            sql_guard.validate("SELECT 1; DROP TABLE taxi")

    def test_rejects_copy_to_file(self):
        # COPY ... TO writes to the filesystem and contains no blocked keyword.
        with pytest.raises(SQLGuardError, match="Only SELECT"):
            sql_guard.validate("COPY (SELECT * FROM taxi) TO '/tmp/leak.csv'")

    def test_rejects_attach(self):
        with pytest.raises(SQLGuardError, match="Only SELECT"):
            sql_guard.validate("ATTACH '/tmp/other.db' AS other")

    def test_rejects_pragma(self):
        with pytest.raises(SQLGuardError, match="Only SELECT"):
            sql_guard.validate("PRAGMA database_list")

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM read_csv('/etc/passwd')",
            "SELECT * FROM read_parquet('/secrets/*.parquet')",
            "SELECT * FROM read_json('/etc/hosts')",
            "SELECT read_text('/etc/passwd') AS leaked",
            "SELECT * FROM glob('/**')",
        ],
    )
    def test_rejects_filesystem_reads_inside_select(self, sql: str):
        # These parse as ordinary SELECTs — only the function denylist stops them.
        with pytest.raises(SQLGuardError, match="disallowed name"):
            sql_guard.validate(sql)

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM duckdb_secrets()",
            "SELECT * FROM duckdb_settings()",
            "SELECT * FROM duckdb_tables()",
            "SELECT * FROM duckdb_databases()",
            "SELECT * FROM duckdb_functions()",
            "SELECT * FROM pragma_database_list()",
            "SELECT * FROM pragma_version()",
            "SELECT version()",
            "SELECT current_setting('memory_limit')",
        ],
    )
    def test_rejects_server_introspection(self, sql: str):
        """All of these are valid SELECTs, so the statement-type check passes them.

        duckdb_secrets() is the sharp one: empty today, but it would hand over
        storage credentials the moment any are configured.
        """
        with pytest.raises(SQLGuardError, match="disallowed name"):
            sql_guard.validate(sql)

    def test_rejects_a_catalog_table_that_needs_no_parentheses(self):
        """Scanning only `name(` would miss this — sqlite_master is a table."""
        with pytest.raises(SQLGuardError, match="sqlite_master"):
            sql_guard.validate("SELECT * FROM sqlite_master")

    @pytest.mark.parametrize("sql", [
        "SELECT * FROM range(5)",
        "SELECT COUNT(*) FROM generate_series(1, 1000000000)",
    ])
    def test_rejects_data_generators(self, sql: str):
        """Nothing to practise with, and unbounded CPU on a public endpoint."""
        with pytest.raises(SQLGuardError, match="disallowed name"):
            sql_guard.validate(sql)

    def test_rejects_the_query_function_that_would_re_enter_sql(self):
        with pytest.raises(SQLGuardError, match="disallowed name"):
            sql_guard.validate("SELECT * FROM query('SELECT 1')")

    def test_prefix_blocking_covers_names_that_do_not_exist_yet(self):
        """A DuckDB upgrade adding duckdb_whatever() is covered without an edit."""
        with pytest.raises(SQLGuardError, match="disallowed name"):
            sql_guard.validate("SELECT * FROM duckdb_some_future_function()")

    def test_rejects_unparseable_sql(self):
        with pytest.raises(SQLGuardError, match="does not parse"):
            sql_guard.validate("SELCT COUNT( FROM taxi")

    def test_rejects_empty(self):
        with pytest.raises(SQLGuardError, match="Empty"):
            sql_guard.validate("   ")

    def test_rejects_prose_from_the_model(self):
        with pytest.raises(SQLGuardError):
            sql_guard.validate("I cannot answer that question.")


class TestEnforceLimit:
    def test_wraps_with_limit(self):
        out = sql_guard.enforce_limit("SELECT * FROM taxi", 100)
        assert out == "SELECT * FROM (SELECT * FROM taxi) AS _guarded LIMIT 101"

    def test_requests_one_extra_row_to_detect_truncation(self):
        assert "LIMIT 6" in sql_guard.enforce_limit("SELECT 1", 5)

    def test_prepare_returns_clean_and_executable(self):
        clean, executable = sql_guard.prepare("```sql\nSELECT 1;\n```", 10)
        assert clean == "SELECT 1"
        assert executable.startswith("SELECT * FROM (SELECT 1)")
