"""
Eval runner for scorer.py — validates that Claude scores job listings
correctly, consistently, and in alignment with candidate preferences.

Run from project root:
    python evals/run_evals.py

Results saved to evals/results/eval_results_YYYYMMDD_HHMMSS.json
"""
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scorer import SYSTEM_PROMPT, load_context

load_dotenv()

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EVALS_DIR = Path(__file__).resolve().parent
TEST_CASES_FILE = EVALS_DIR / "scorer_evals.json"
RESULTS_DIR = EVALS_DIR / "results"
MODEL = "claude-sonnet-4-6"

logging.basicConfig(level=logging.WARNING)

REQUIRED_FIELDS = {
    "score", "rationale", "match_tags", "red_flags",
    "ai_opportunity", "alignment", "gaps",
}


def load_test_cases() -> list[dict]:
    return json.loads(TEST_CASES_FILE.read_text(encoding="utf-8"))["test_cases"]


def score_one(client: anthropic.Anthropic, cached_system: list[dict], job: dict) -> dict | None:
    user_content = (
        f"Score this job posting for the candidate.\n\n"
        f"Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"Location: {job.get('location', '')}\n"
        f"Applicants: {job.get('applicant_count', 'unknown')}\n\n"
        f"Full Description:\n{job.get('description', '')[:6000]}"
    )
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=700,
                system=cached_system,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())
            return json.loads(raw)
        except (json.JSONDecodeError, anthropic.APIError):
            pass
        if attempt < 2:
            time.sleep(2 ** attempt)
    return None


def run_checks(tc: dict, result: dict) -> dict:
    expected = tc["expected"]
    checks = {}
    failures = []

    # Schema
    missing = REQUIRED_FIELDS - set(result.keys())
    if missing:
        checks["schema"] = "fail"
        failures.append(f"Missing fields: {', '.join(sorted(missing))}")
    else:
        checks["schema"] = "pass"

    score = result.get("score", 0)
    try:
        score = int(score)
    except (ValueError, TypeError):
        score = 0

    # Accuracy
    score_min = expected.get("score_min", 1)
    score_max = expected.get("score_max", 10)
    if score_min <= score <= score_max:
        checks["accuracy"] = "pass"
    else:
        checks["accuracy"] = "fail"
        failures.append(f"Score {score}/10 outside expected range [{score_min}-{score_max}]")

    # AI opportunity
    if "ai_opportunity" in expected:
        expected_ai = expected["ai_opportunity"]
        actual_ai = bool(result.get("ai_opportunity", False))
        if actual_ai == bool(expected_ai):
            checks["ai_opportunity"] = "pass"
        else:
            checks["ai_opportunity"] = "fail"
            failures.append(f"ai_opportunity={actual_ai} but expected {expected_ai}")

    # Match tags (at least one required tag must appear somewhere in actual tags)
    required_tags = expected.get("required_match_tags", [])
    if required_tags:
        actual_tags_str = " ".join(t.lower() for t in result.get("match_tags", []))
        matched = any(req.lower() in actual_tags_str for req in required_tags)
        checks["match_tags"] = "pass" if matched else "fail"
        if not matched:
            failures.append(
                f"None of {required_tags} found in {result.get('match_tags', [])}"
            )
    else:
        checks["match_tags"] = "n/a"

    # Red flags expected
    if expected.get("red_flags_expected", False):
        if result.get("red_flags"):
            checks["red_flags"] = "pass"
        else:
            checks["red_flags"] = "fail"
            failures.append("red_flags is empty but expected non-empty")
    else:
        checks["red_flags"] = "n/a"

    # Forbidden tags (none of these should appear as a match_tag)
    forbidden_tags = expected.get("forbidden_match_tags", [])
    if forbidden_tags:
        actual_tags_lower = [t.lower() for t in result.get("match_tags", [])]
        found = [f for f in forbidden_tags if any(f.lower() in t for t in actual_tags_lower)]
        checks["forbidden_tags"] = "fail" if found else "pass"
        if found:
            failures.append(f"Forbidden tags found in match_tags: {found}")
    else:
        checks["forbidden_tags"] = "n/a"

    overall = "fail" if any(v == "fail" for v in checks.values()) else "pass"
    return {"checks": checks, "failures": failures, "overall": overall, "score": score}


def run_consistency_test(
    client: anthropic.Anthropic, cached_system: list[dict], tc: dict
) -> dict:
    scores = []
    for i in range(3):
        result = score_one(client, cached_system, tc["job"])
        if result:
            try:
                scores.append(int(result.get("score", 0)))
            except (ValueError, TypeError):
                pass
        if i < 2:
            time.sleep(1)

    if len(scores) < 3:
        return {
            "checks": {"consistency": "fail"},
            "failures": [f"Only {len(scores)}/3 API calls succeeded"],
            "overall": "fail",
            "scores": scores,
            "variance": None,
        }

    variance = max(scores) - min(scores)
    passed = variance <= 1
    return {
        "checks": {"consistency": "pass" if passed else "fail"},
        "failures": [] if passed else [f"Variance {variance} > 1 allowed (scores: {scores})"],
        "overall": "pass" if passed else "fail",
        "scores": scores,
        "variance": variance,
    }


def print_case_result(tc: dict, outcome: dict, result: dict | None):
    job = tc["job"]
    title_str = f"{tc['id']} | {job['title']} at {job['company']}"
    status = "PASS" if outcome["overall"] == "pass" else "FAIL"
    checks = outcome["checks"]
    failures = outcome["failures"]

    print(f"{'─'*65}")
    print(f"{title_str} | {status}")

    if tc.get("eval_type") == "consistency":
        scores = outcome.get("scores", [])
        variance = outcome.get("variance")
        sym = "✓" if checks.get("consistency") == "pass" else "✗"
        print(f"  Consistency: runs={scores}, variance={variance} {sym}")
    else:
        score = outcome.get("score", "?")
        exp = tc["expected"]
        sym = "✓" if checks.get("accuracy") == "pass" else "✗"
        print(f"  Score: {score}/10 (expected {exp['score_min']}-{exp['score_max']}) {sym}")

        schema_sym = "✓" if checks.get("schema") == "pass" else "✗"
        print(f"  Schema: {'all fields present' if checks.get('schema') == 'pass' else 'MISSING FIELDS'} {schema_sym}")

        if checks.get("ai_opportunity") not in ("n/a", None):
            ai_sym = "✓" if checks["ai_opportunity"] == "pass" else "✗"
            actual_ai = result.get("ai_opportunity") if result else "?"
            print(f"  AI opportunity: {actual_ai} {ai_sym}")

        if checks.get("match_tags") != "n/a":
            tags_sym = "✓" if checks.get("match_tags") == "pass" else "✗"
            actual_tags = result.get("match_tags", []) if result else []
            print(f"  Match tags: {actual_tags} {tags_sym}")

        if checks.get("red_flags") != "n/a":
            rf_sym = "✓" if checks.get("red_flags") == "pass" else "✗"
            actual_rf = result.get("red_flags", []) if result else []
            print(f"  Red flags: {actual_rf} {rf_sym}")

        if checks.get("forbidden_tags") not in ("n/a", None, "pass"):
            print(f"  Forbidden tags: FOUND ✗")

    if failures:
        fm = tc.get("failure_mode_tested", "none")
        for f in failures:
            label = f"  ✗ {f}"
            if fm and fm != "none":
                label += f"  ← {fm}"
            print(label)

    if result and result.get("rationale"):
        snippet = result["rationale"][:110]
        if len(result["rationale"]) > 110:
            snippet += "…"
        print(f"  Rationale: {snippet}")


def print_summary(all_results: list[dict], test_cases: list[dict]):
    print(f"\n{'═'*65}")
    print(f"EVAL SUMMARY — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'─'*65}")

    total = len(all_results)
    overall_pass = sum(1 for r in all_results if r["overall"] == "pass")
    pct = round(100 * overall_pass / total) if total else 0
    print(f"Total test cases:    {total}")
    print(f"Overall pass rate:   {overall_pass}/{total} ({pct}%)")
    print()

    def check_stats(key: str) -> tuple[int, int]:
        relevant = [r for r in all_results if r.get("checks", {}).get(key) in ("pass", "fail")]
        passed = sum(1 for r in relevant if r["checks"].get(key) == "pass")
        return passed, len(relevant)

    print("By check type:")
    for label, key in [
        ("Schema conformance", "schema"),
        ("Score accuracy    ", "accuracy"),
        ("AI opportunity    ", "ai_opportunity"),
        ("Match tags        ", "match_tags"),
        ("Red flags         ", "red_flags"),
        ("Forbidden tags    ", "forbidden_tags"),
    ]:
        p, t = check_stats(key)
        if t:
            pct_k = round(100 * p / t)
            print(f"  {label}:  {p}/{t} ({pct_k}%)")

    consistency_r = next((r for r in all_results if r.get("test_id") == "tc_013"), None)
    if consistency_r:
        c_pass = consistency_r.get("checks", {}).get("consistency") == "pass"
        variance = consistency_r.get("variance", "?")
        print(f"  Consistency (tc_013):      {'pass' if c_pass else 'fail'} (variance: {variance} pts)")

    failures_list = [r for r in all_results if r["overall"] == "fail"]
    if failures_list:
        print()
        print("Failures requiring attention:")
        for r in failures_list:
            tc = next((t for t in test_cases if t["id"] == r.get("test_id")), {})
            job = tc.get("job", {})
            title = f"{job.get('title', '?')} at {job.get('company', '?')}"
            fm = tc.get("failure_mode_tested", "none")
            fm_note = f" [{fm}]" if fm and fm != "none" else ""
            print(f"  {r.get('test_id')} — {title}{fm_note}")
            for note in r.get("failures", [])[:2]:
                print(f"    {note[:90]}")
    else:
        print()
        print("All test cases passed!")

    print(f"{'═'*65}")


def main():
    test_cases = load_test_cases()
    print(f"\nLoaded {len(test_cases)} test case(s) from scorer_evals.json")
    print(f"Model: {MODEL}")
    print(f"Running evals...\n")

    RESULTS_DIR.mkdir(exist_ok=True)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    context = load_context()
    cached_system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT + "\n\n" + context,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    all_results = []

    for tc in test_cases:
        tc_id = tc["id"]
        job = tc["job"]
        title_str = f"{job.get('title', '')} at {job.get('company', '')}"

        if tc.get("eval_type") == "consistency":
            outcome = run_consistency_test(client, cached_system, tc)
            print_case_result(tc, outcome, None)
            all_results.append({
                "test_id": tc_id,
                "title": title_str,
                "source": tc.get("source"),
                "eval_type": "consistency",
                "failure_mode_tested": tc.get("failure_mode_tested", "none"),
                "scores": outcome.get("scores", []),
                "variance": outcome.get("variance"),
                "checks": outcome["checks"],
                "overall": outcome["overall"],
                "failures": outcome.get("failures", []),
                "claude_full_response": None,
            })
        else:
            result = score_one(client, cached_system, job)
            if result is None:
                print(f"{'─'*65}")
                print(f"{tc_id} | {title_str} | ERROR — API call failed")
                all_results.append({
                    "test_id": tc_id,
                    "title": title_str,
                    "source": tc.get("source"),
                    "eval_type": tc.get("eval_type", "accuracy"),
                    "failure_mode_tested": tc.get("failure_mode_tested", "none"),
                    "claude_score": None,
                    "expected_range": [tc["expected"]["score_min"], tc["expected"]["score_max"]],
                    "checks": {"schema": "fail"},
                    "overall": "fail",
                    "failures": ["API call failed after 3 retries"],
                    "claude_full_response": None,
                })
                continue

            outcome = run_checks(tc, result)
            print_case_result(tc, outcome, result)
            all_results.append({
                "test_id": tc_id,
                "title": title_str,
                "source": tc.get("source"),
                "eval_type": tc.get("eval_type", "accuracy"),
                "failure_mode_tested": tc.get("failure_mode_tested", "none"),
                "claude_score": outcome.get("score"),
                "expected_range": [tc["expected"]["score_min"], tc["expected"]["score_max"]],
                "checks": outcome["checks"],
                "overall": outcome["overall"],
                "failures": outcome.get("failures", []),
                "claude_full_response": result,
            })

    print()
    print_summary(all_results, test_cases)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"eval_results_{timestamp}.json"
    results_data = {
        "run_date": datetime.now().isoformat(),
        "model": MODEL,
        "total_cases": len(all_results),
        "overall_pass_rate": round(
            sum(1 for r in all_results if r["overall"] == "pass") / len(all_results), 3
        ) if all_results else 0,
        "results": all_results,
    }
    results_file.write_text(
        json.dumps(results_data, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nResults saved to: evals/results/{results_file.name}")

    _append_history(all_results, results_data)


def _append_history(all_results: list[dict], results_data: dict):
    history_file = EVALS_DIR / "eval_history.csv"

    total = results_data["total_cases"]
    pass_rate = results_data["overall_pass_rate"]

    def check_rate(key: str) -> str:
        relevant = [r for r in all_results if r.get("checks", {}).get(key) in ("pass", "fail")]
        if not relevant:
            return "n/a"
        passed = sum(1 for r in relevant if r["checks"].get(key) == "pass")
        return str(round(passed / len(relevant), 2))

    schema_rate = check_rate("schema")
    accuracy_rate = check_rate("accuracy")

    consistency_r = next((r for r in all_results if r.get("test_id") == "tc_013"), None)
    variance = str(consistency_r["variance"]) if consistency_r and consistency_r.get("variance") is not None else "n/a"

    failed_ids = [r["test_id"] for r in all_results if r["overall"] == "fail"]
    failures_str = "|".join(failed_ids) if failed_ids else "none"

    date_str = datetime.now().strftime("%Y-%m-%d")
    row = f"{date_str},{pass_rate},{total},{schema_rate},{accuracy_rate},{variance},{failures_str}\n"

    write_header = not history_file.exists()
    with history_file.open("a", encoding="utf-8") as f:
        if write_header:
            f.write("date,pass_rate,total_cases,schema_pass,accuracy_pass,consistency_variance,failures\n")
        f.write(row)

    print(f"History appended to: evals/eval_history.csv")


if __name__ == "__main__":
    main()
