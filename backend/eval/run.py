"""Evaluation harness for the NL→SQL pipeline.

Measures **execution accuracy**: a generated query counts as correct when its
result set matches the result set of hand-written reference SQL. SQL is not
compared as text — `COUNT(*)` and `SUM(1)` are both right, and any string
metric would call one of them wrong.

Comparison rules, chosen to punish real errors and forgive cosmetic ones:

* Rows are compared as an order-insensitive multiset, since `GROUP BY` output
  order is not meaningful unless the question asked for a ranking. Cases that
  do ask for a ranking pin the order with `LIMIT`, so a wrong ordering still
  produces a wrong row set and is still caught.
* Floats are rounded to 2 decimal places, so "did it round the average?" is
  not scored as a correctness failure.
* Column *names* and column *order* are ignored, column *count* is not:
  aliasing `avg_fare` as `average_fare` is fine and so is selecting the group
  key second, but returning an extra column is not.

Usage:
    python -m eval.run                  # full run (needs GROQ_API_KEY)
    python -m eval.run --limit 5        # quick smoke run
    python -m eval.run --check          # no LLM: verify reference SQL only
    python -m eval.run --out ../docs/eval-report.md
"""

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

# Allow `python -m eval.run` from the backend directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

# On Windows, redirecting stdout to a file selects cp1252, which cannot encode
# the characters used in the report. Force UTF-8 so `> report.log` behaves the
# same on every platform.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402
import query_engine  # noqa: E402
import sql_guard  # noqa: E402
from sql_guard import SQLGuardError  # noqa: E402

DATASET_PATH = Path(__file__).parent / "dataset.json"
FLOAT_PRECISION = 2


def load_cases() -> list[dict]:
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return data["cases"]


def _normalize_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return round(float(value), FLOAT_PRECISION)
    return str(value)


def _canonicalize(rows: list[list]) -> list[tuple]:
    """Put a result set into a form that ignores presentation-only differences.

    Columns are reordered into a deterministic order derived from their own
    values, then rows are sorted. That makes the comparison blind to both
    column order and row order — `SELECT passenger_count, avg_total` and
    `SELECT avg_total, passenger_count` answer the same question — while still
    keeping each row's values bound together, so a genuinely mismatched pairing
    is still caught.
    """
    normalized = [[_normalize_value(v) for v in row] for row in rows]
    if not normalized:
        return []

    columns = list(zip(*normalized, strict=True))
    order = sorted(range(len(columns)), key=lambda i: str(columns[i]))
    reordered = [tuple(row[i] for i in order) for row in normalized]
    return sorted(reordered, key=lambda t: tuple(str(v) for v in t))


def results_match(expected: dict, actual: dict) -> bool:
    if "error" in expected or "error" in actual:
        return False
    if len(expected["columns"]) != len(actual["columns"]):
        return False
    return _canonicalize(expected["rows"]) == _canonicalize(actual["rows"])


def evaluate_case(case: dict) -> dict:
    """Run one case end to end and score it."""
    outcome = {
        "id": case["id"],
        "question": case["question"],
        "category": case["category"],
        "difficulty": case["difficulty"],
        "reference_sql": case["reference_sql"],
        "generated_sql": None,
        "valid_sql": False,
        "correct": False,
        "attempts": 0,
        "latency_ms": 0,
        "failure": None,
    }

    expected = query_engine.run_query(case["reference_sql"])
    if "error" in expected:
        outcome["failure"] = f"reference SQL is broken: {expected['error']}"
        return outcome

    started = time.perf_counter()
    try:
        # explain=False: the explanation is a separate LLM call that costs
        # time and money and has no bearing on SQL correctness.
        out = query_engine.run_pipeline(case["question"], explain=False)
    except SQLGuardError as exc:
        outcome["latency_ms"] = int((time.perf_counter() - started) * 1000)
        outcome["failure"] = f"rejected by guard: {exc}"
        return outcome
    except Exception as exc:
        outcome["latency_ms"] = int((time.perf_counter() - started) * 1000)
        outcome["failure"] = f"{type(exc).__name__}: {exc}"
        return outcome

    outcome["latency_ms"] = int((time.perf_counter() - started) * 1000)
    outcome["generated_sql"] = out["sql"]
    outcome["attempts"] = out.get("attempts", 1)

    if "error" in out["result"]:
        outcome["failure"] = f"execution error: {out['result']['error']}"
        return outcome

    outcome["valid_sql"] = True
    outcome["correct"] = results_match(expected, out["result"])
    if not outcome["correct"]:
        outcome["failure"] = (
            f"wrong result: expected {len(expected['rows'])} row(s) "
            f"{expected['columns']}, got {len(out['result']['rows'])} row(s) "
            f"{out['result']['columns']}"
        )
    return outcome


def check_references(cases: list[dict]) -> int:
    """Execute every reference query without calling the LLM.

    This is what CI runs: it proves the golden set stays valid against the
    schema without needing an API key or spending money.
    """
    failures = 0
    for case in cases:
        try:
            sql_guard.validate(case["reference_sql"])
        except SQLGuardError as exc:
            print(f"FAIL {case['id']}: reference SQL rejected by guard - {exc}")
            failures += 1
            continue
        result = query_engine.run_query(case["reference_sql"])
        if "error" in result:
            print(f"FAIL {case['id']}: {result['error']}")
            failures += 1
        else:
            print(f"ok   {case['id']}: {len(result['rows'])} row(s)")
    print(f"\n{len(cases) - failures}/{len(cases)} reference queries valid")
    return failures


def summarize(outcomes: list[dict]) -> dict:
    total = len(outcomes)
    correct = sum(o["correct"] for o in outcomes)
    valid = sum(o["valid_sql"] for o in outcomes)
    latencies = sorted(o["latency_ms"] for o in outcomes if o["latency_ms"])

    by_group: dict[str, dict[str, dict]] = {"category": defaultdict(lambda: {"total": 0, "correct": 0}),
                                            "difficulty": defaultdict(lambda: {"total": 0, "correct": 0})}
    for o in outcomes:
        for dimension in ("category", "difficulty"):
            bucket = by_group[dimension][o[dimension]]
            bucket["total"] += 1
            bucket["correct"] += int(o["correct"])

    return {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": config.MODEL_NAME,
        "total_cases": total,
        "execution_accuracy": round(correct / total, 3) if total else 0.0,
        "valid_sql_rate": round(valid / total, 3) if total else 0.0,
        # "Needed a retry" conflates two opposite outcomes, so they are counted
        # apart: a question the model fixed itself is a success story, one that
        # burned every attempt is a failure.
        "needed_self_correction": sum(1 for o in outcomes if o["attempts"] > 1),
        "recovered_by_self_correction": sum(
            1 for o in outcomes if o["attempts"] > 1 and o["valid_sql"]
        ),
        "exhausted_retries": sum(
            1 for o in outcomes if o["attempts"] > 1 and not o["valid_sql"]
        ),
        "median_latency_ms": int(statistics.median(latencies)) if latencies else 0,
        "p95_latency_ms": latencies[int(len(latencies) * 0.95) - 1] if latencies else 0,
        "by_category": {k: dict(v) for k, v in by_group["category"].items()},
        "by_difficulty": {k: dict(v) for k, v in by_group["difficulty"].items()},
    }


def _pct(correct: int, total: int) -> str:
    return f"{round(100 * correct / total)}%" if total else "—"


def render_markdown(summary: dict, outcomes: list[dict]) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"_Generated {summary['timestamp']} · model `{summary['model']}`_",
        "",
        "Execution accuracy on a hand-written golden set: a generated query is",
        "correct when its result set matches the reference query's result set.",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Execution accuracy | **{_pct(round(summary['execution_accuracy'] * summary['total_cases']), summary['total_cases'])}** |",
        f"| Valid SQL rate | {_pct(round(summary['valid_sql_rate'] * summary['total_cases']), summary['total_cases'])} |",
        f"| Cases | {summary['total_cases']} |",
        f"| Recovered by self-correction | {summary.get('recovered_by_self_correction', 0)} |",
        f"| Exhausted all retries | {summary.get('exhausted_retries', 0)} |",
        f"| Median latency | {summary['median_latency_ms']} ms |",
        f"| p95 latency | {summary['p95_latency_ms']} ms |",
        "",
        "## By category",
        "",
        "| Category | Accuracy | Cases |",
        "|----------|----------|-------|",
    ]
    for name, stats in sorted(summary["by_category"].items()):
        lines.append(f"| {name} | {_pct(stats['correct'], stats['total'])} | {stats['total']} |")

    lines += ["", "## By difficulty", "", "| Difficulty | Accuracy | Cases |", "|------------|----------|-------|"]
    for name in ("easy", "medium", "hard"):
        stats = summary["by_difficulty"].get(name)
        if stats:
            lines.append(f"| {name} | {_pct(stats['correct'], stats['total'])} | {stats['total']} |")

    failures = [o for o in outcomes if not o["correct"]]
    lines += ["", f"## Failures ({len(failures)})", ""]
    if not failures:
        lines.append("None.")
    for o in failures:
        lines += [
            f"### `{o['id']}` — {o['question']}",
            "",
            f"- **Why:** {o['failure']}",
            f"- **Expected:** `{o['reference_sql']}`",
            f"- **Generated:** `{o['generated_sql'] or '(none)'}`",
            "",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the NL→SQL pipeline.")
    parser.add_argument("--limit", type=int, help="only run the first N cases")
    parser.add_argument("--category", help="only run cases in this category")
    parser.add_argument("--check", action="store_true",
                        help="verify reference SQL only; makes no LLM calls")
    parser.add_argument("--out", type=Path, help="write a markdown report here")
    parser.add_argument("--json", dest="json_out", type=Path, help="write raw results here")
    parser.add_argument("--from-json", type=Path,
                        help="re-render a report from a previous run's raw results, "
                             "without calling the LLM again")
    args = parser.parse_args()

    if args.from_json:
        stored = json.loads(args.from_json.read_text(encoding="utf-8"))
        outcomes = stored["outcomes"]
        summary = {**summarize(outcomes), "timestamp": stored["summary"]["timestamp"],
                   "model": stored["summary"]["model"]}
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(render_markdown(summary, outcomes), encoding="utf-8")
            print(f"report written to {args.out}")
        return 0

    cases = load_cases()
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if args.limit:
        cases = cases[: args.limit]

    if args.check:
        return 1 if check_references(cases) else 0

    if not config.GROQ_API_KEY:
        print("GROQ_API_KEY is not set. Use --check to validate the dataset without an API key.")
        return 2

    outcomes = []
    for i, case in enumerate(cases, 1):
        outcome = evaluate_case(case)
        outcomes.append(outcome)
        mark = "PASS" if outcome["correct"] else "FAIL"
        print(f"[{i}/{len(cases)}] {mark} {case['id']}: {case['question']}")
        if outcome["failure"]:
            print(f"         {outcome['failure']}")

    summary = summarize(outcomes)
    print("\n" + "=" * 60)
    print(f"Execution accuracy : {summary['execution_accuracy']:.1%}")
    print(f"Valid SQL rate     : {summary['valid_sql_rate']:.1%}")
    print(f"Self-corrected     : {summary['recovered_by_self_correction']} recovered, "
          f"{summary['exhausted_retries']} gave up")
    print(f"Median latency     : {summary['median_latency_ms']} ms")
    print("=" * 60)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(render_markdown(summary, outcomes), encoding="utf-8")
        print(f"report written to {args.out}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"summary": summary, "outcomes": outcomes}, indent=2), encoding="utf-8"
        )
        print(f"raw results written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
