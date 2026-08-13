"""Tests for the evaluation harness.

The `--check` path is what CI runs: it proves every reference query in the
golden set still parses, passes the guard and executes against the schema,
without needing an API key or spending anything.
"""

from unittest.mock import patch

import pytest

from eval import run as evalrun


@pytest.fixture(scope="module")
def cases():
    return evalrun.load_cases()


class TestDataset:
    def test_dataset_is_not_empty(self, cases):
        assert len(cases) >= 30

    def test_ids_are_unique(self, cases):
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids))

    def test_questions_are_unique(self, cases):
        questions = [c["question"].lower() for c in cases]
        assert len(questions) == len(set(questions))

    def test_every_case_has_required_fields(self, cases):
        for case in cases:
            assert {"id", "question", "category", "difficulty", "reference_sql"} <= set(case)

    def test_difficulties_are_known(self, cases):
        assert {c["difficulty"] for c in cases} <= {"easy", "medium", "hard"}

    def test_covers_several_categories(self, cases):
        assert len({c["category"] for c in cases}) >= 5

    def test_every_reference_query_runs(self, cases):
        """The golden set must stay valid as the schema evolves."""
        assert evalrun.check_references(cases) == 0


class TestNoTestSetLeakage:
    """The few-shot exemplars must never quote the evaluation set.

    Demonstrating conventions is prompt engineering; demonstrating the answers
    is training on the test set, and would make the accuracy number a lie.
    """

    def test_few_shot_questions_are_not_eval_questions(self, cases):
        import query_engine

        eval_questions = {c["question"].lower().rstrip("?").strip() for c in cases}
        for question, _ in query_engine._FEW_SHOT:
            assert question.lower().rstrip("?").strip() not in eval_questions

    def test_few_shot_sql_is_not_reference_sql(self, cases):
        import query_engine

        reference = {" ".join(c["reference_sql"].lower().split()) for c in cases}
        for _, sql in query_engine._FEW_SHOT:
            assert " ".join(sql.lower().split()) not in reference


class TestResultComparison:
    def test_identical_results_match(self):
        result = {"columns": ["a"], "rows": [[1]], "row_count": 1}
        assert evalrun.results_match(result, result)

    def test_row_order_is_ignored(self):
        expected = {"columns": ["a"], "rows": [[1], [2]], "row_count": 2}
        actual = {"columns": ["a"], "rows": [[2], [1]], "row_count": 2}
        assert evalrun.results_match(expected, actual)

    def test_column_order_is_ignored(self):
        """Selecting the group key second still answers the question."""
        expected = {"columns": ["passenger_count", "avg_total"],
                    "rows": [[1, 20.5], [2, 31.0]], "row_count": 2}
        actual = {"columns": ["avg_total", "passenger_count"],
                  "rows": [[20.5, 1], [31.0, 2]], "row_count": 2}
        assert evalrun.results_match(expected, actual)

    def test_scrambled_row_pairings_still_fail(self):
        """Order-insensitivity must not become blindness to wrong pairings."""
        expected = {"columns": ["k", "v"], "rows": [[1, 10], [2, 20]], "row_count": 2}
        actual = {"columns": ["k", "v"], "rows": [[1, 20], [2, 10]], "row_count": 2}
        assert not evalrun.results_match(expected, actual)

    def test_column_names_are_ignored(self):
        expected = {"columns": ["avg_fare"], "rows": [[14.2]], "row_count": 1}
        actual = {"columns": ["average_fare"], "rows": [[14.2]], "row_count": 1}
        assert evalrun.results_match(expected, actual)

    def test_rounding_differences_are_forgiven(self):
        expected = {"columns": ["a"], "rows": [[14.23]], "row_count": 1}
        actual = {"columns": ["a"], "rows": [[14.234567]], "row_count": 1}
        assert evalrun.results_match(expected, actual)

    def test_meaningfully_different_numbers_do_not_match(self):
        expected = {"columns": ["a"], "rows": [[14.23]], "row_count": 1}
        actual = {"columns": ["a"], "rows": [[15.99]], "row_count": 1}
        assert not evalrun.results_match(expected, actual)

    def test_extra_column_does_not_match(self):
        expected = {"columns": ["a"], "rows": [[1]], "row_count": 1}
        actual = {"columns": ["a", "b"], "rows": [[1, 2]], "row_count": 1}
        assert not evalrun.results_match(expected, actual)

    def test_missing_rows_do_not_match(self):
        expected = {"columns": ["a"], "rows": [[1], [2]], "row_count": 2}
        actual = {"columns": ["a"], "rows": [[1]], "row_count": 1}
        assert not evalrun.results_match(expected, actual)

    def test_errors_never_match(self):
        ok = {"columns": ["a"], "rows": [[1]], "row_count": 1}
        assert not evalrun.results_match(ok, {"error": "boom"})
        assert not evalrun.results_match({"error": "boom"}, ok)


class TestEvaluateCase:
    CASE = {
        "id": "t-1",
        "question": "How many trips?",
        "category": "counting",
        "difficulty": "easy",
        "reference_sql": "SELECT COUNT(*) AS c FROM taxi",
    }

    def test_scores_a_correct_answer(self):
        with patch("query_engine.run_pipeline",
                   return_value={"sql": "SELECT COUNT(1) AS n FROM taxi",
                                 "result": {"columns": ["n"], "rows": [[5]], "row_count": 1},
                                 "attempts": 1}):
            outcome = evalrun.evaluate_case(self.CASE)
        assert outcome["correct"] and outcome["valid_sql"]

    def test_scores_a_wrong_answer(self):
        with patch("query_engine.run_pipeline",
                   return_value={"sql": "SELECT 999 AS n", "attempts": 1,
                                 "result": {"columns": ["n"], "rows": [[999]], "row_count": 1}}):
            outcome = evalrun.evaluate_case(self.CASE)
        assert outcome["valid_sql"] and not outcome["correct"]
        assert "wrong result" in outcome["failure"]

    def test_records_execution_failure(self):
        with patch("query_engine.run_pipeline",
                   return_value={"sql": "SELECT nope FROM taxi", "attempts": 3,
                                 "result": {"error": "no such column"}}):
            outcome = evalrun.evaluate_case(self.CASE)
        assert not outcome["valid_sql"]
        assert "execution error" in outcome["failure"]

    def test_records_attempts(self):
        with patch("query_engine.run_pipeline",
                   return_value={"sql": "SELECT COUNT(*) AS c FROM taxi", "attempts": 2,
                                 "result": {"columns": ["c"], "rows": [[5]], "row_count": 1}}):
            outcome = evalrun.evaluate_case(self.CASE)
        assert outcome["attempts"] == 2

    def test_does_not_pay_for_explanations(self):
        with patch("query_engine.run_pipeline",
                   return_value={"sql": "SELECT COUNT(*) AS c FROM taxi", "attempts": 1,
                                 "result": {"columns": ["c"], "rows": [[5]], "row_count": 1}}) as pipeline:
            evalrun.evaluate_case(self.CASE)
        assert pipeline.call_args[1]["explain"] is False

    def test_broken_reference_sql_is_reported(self):
        outcome = evalrun.evaluate_case({**self.CASE, "reference_sql": "SELECT nope FROM taxi"})
        assert "reference SQL is broken" in outcome["failure"]


class TestSummary:
    def _outcome(self, **kwargs):
        base = {"correct": True, "valid_sql": True, "attempts": 1, "latency_ms": 100,
                "category": "counting", "difficulty": "easy"}
        return {**base, **kwargs}

    def test_accuracy_is_the_fraction_correct(self):
        outcomes = [self._outcome(), self._outcome(correct=False),
                    self._outcome(), self._outcome()]
        assert evalrun.summarize(outcomes)["execution_accuracy"] == 0.75

    def test_counts_self_corrections(self):
        outcomes = [self._outcome(attempts=2), self._outcome()]
        assert evalrun.summarize(outcomes)["needed_self_correction"] == 1

    def test_separates_recovery_from_giving_up(self):
        """A retry that worked and a retry that ran out are opposite outcomes."""
        outcomes = [
            self._outcome(attempts=2, valid_sql=True),                    # recovered
            self._outcome(attempts=3, valid_sql=False, correct=False),    # gave up
            self._outcome(attempts=1),                                    # first try
        ]
        summary = evalrun.summarize(outcomes)
        assert summary["recovered_by_self_correction"] == 1
        assert summary["exhausted_retries"] == 1
        assert summary["needed_self_correction"] == 2

    def test_breaks_down_by_category(self):
        outcomes = [self._outcome(category="counting"),
                    self._outcome(category="ratio", correct=False)]
        by_category = evalrun.summarize(outcomes)["by_category"]
        assert by_category["counting"] == {"total": 1, "correct": 1}
        assert by_category["ratio"] == {"total": 1, "correct": 0}

    def test_handles_an_empty_run(self):
        summary = evalrun.summarize([])
        assert summary["execution_accuracy"] == 0.0
        assert summary["total_cases"] == 0

    def test_markdown_report_renders(self):
        outcomes = [self._outcome(), self._outcome(correct=False, failure="wrong result",
                                                   id="x", question="q", reference_sql="SELECT 1",
                                                   generated_sql="SELECT 2")]
        markdown = evalrun.render_markdown(evalrun.summarize(outcomes), outcomes)
        assert "# Evaluation report" in markdown
        assert "Execution accuracy" in markdown
        assert "Failures (1)" in markdown
