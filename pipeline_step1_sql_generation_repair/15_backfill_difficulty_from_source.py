import argparse
import json
import re
from collections import Counter
from pathlib import Path


def parse_expected_diff(source_entry):
    if not isinstance(source_entry, dict):
        return None

    model1_db_id = source_entry.get("model1_db_id")
    if isinstance(model1_db_id, str):
        m = re.search(r"_diff(\d+)_", model1_db_id)
        if m:
            return int(m.group(1))

    meta = source_entry.get("model1_meta")
    if isinstance(meta, dict):
        text = meta.get("prompt_id") or meta.get("run_id") or ""
        if isinstance(text, str):
            m = re.search(r"diff(\d+)", text)
            if m:
                return int(m.group(1))

    return None


def build_test7(expected_diff, actual_diff):
    passed = isinstance(expected_diff, int) and isinstance(actual_diff, int) and expected_diff == actual_diff
    if passed:
        return {"passed": True, "detail": f"difficulty matches diff{expected_diff}"}
    if expected_diff is None:
        return {"passed": False, "detail": "diff number missing in source meta"}
    if not isinstance(actual_diff, int):
        return {
            "passed": False,
            "detail": {
                "expected": expected_diff,
                "actual_diff": actual_diff,
                "reason": "query_difficulty missing or not an integer",
            },
        }
    return {"passed": False, "detail": {"expected": expected_diff, "actual_diff": actual_diff}}


def recompute_summary(analysis_obj):
    analysis = analysis_obj.get("analysis", [])
    summary = analysis_obj.get("summary") if isinstance(analysis_obj.get("summary"), dict) else {}
    test_sequence = summary.get("test_sequence")
    if not isinstance(test_sequence, list) or not test_sequence:
        test_sequence = [
            "test1_parse",
            "test2_validate",
            "test3_execution",
            "test4_preview",
            "test5_foreign_keys",
            "test6_lint",
            "test7_difficulty",
        ]

    per_test_pass_counts = {
        test: sum(
            1
            for entry in analysis
            if isinstance(entry, dict)
            and isinstance(entry.get("tests"), dict)
            and isinstance(entry["tests"].get(test), dict)
            and entry["tests"][test].get("passed") is True
        )
        for test in test_sequence
    }

    combinations = Counter(
        tuple(
            bool(
                isinstance(entry.get("tests"), dict)
                and isinstance(entry["tests"].get(test), dict)
                and entry["tests"][test].get("passed") is True
            )
            for test in test_sequence
        )
        for entry in analysis
        if isinstance(entry, dict)
    )

    total = len(analysis)
    combination_details = [
        {
            "pattern": {test: flag for test, flag in zip(test_sequence, pattern)},
            "count": count,
            "share": (count / total) if total else 0.0,
        }
        for pattern, count in combinations.most_common()
    ]

    analysis_obj["summary"] = {
        "test_sequence": test_sequence,
        "per_test_pass_counts": per_test_pass_counts,
        "combination_details": combination_details,
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill test7_difficulty from source meta and refresh summary.")
    parser.add_argument("--analysis-file", required=True)
    parser.add_argument("--source-file", required=True)
    parser.add_argument(
        "--step2-file",
        required=False,
        help="Optional step2 output2 list file that contains query_difficulty per index.",
    )
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args()

    analysis_path = Path(args.analysis_file)
    source_path = Path(args.source_file)
    step2_path = Path(args.step2_file) if args.step2_file else None
    output_path = Path(args.output_file)

    analysis_obj = json.load(analysis_path.open("r", encoding="utf-8"))
    source_entries = json.load(source_path.open("r", encoding="utf-8"))
    step2_entries = None
    if step2_path:
        step2_entries = json.load(step2_path.open("r", encoding="utf-8"))

    if not isinstance(analysis_obj, dict) or not isinstance(analysis_obj.get("analysis"), list):
        raise ValueError("analysis-file must be object with list field 'analysis'")
    if not isinstance(source_entries, list):
        raise ValueError("source-file must be a list")
    if step2_entries is not None and not isinstance(step2_entries, list):
        raise ValueError("step2-file must be a list")

    analysis_entries = analysis_obj["analysis"]
    if len(analysis_entries) != len(source_entries):
        raise ValueError(f"entry count mismatch: analysis={len(analysis_entries)} source={len(source_entries)}")
    if step2_entries is not None and len(step2_entries) != len(analysis_entries):
        raise ValueError(f"entry count mismatch: analysis={len(analysis_entries)} step2={len(step2_entries)}")

    before_pass = 0
    for e in analysis_entries:
        t = (e.get("tests") or {}).get("test7_difficulty")
        if isinstance(t, dict) and t.get("passed") is True:
            before_pass += 1

    missing_actual = 0
    for i, (analysis_entry, source_entry) in enumerate(zip(analysis_entries, source_entries)):
        if not isinstance(analysis_entry, dict):
            raise ValueError(f"analysis entry {i} is not an object")

        tests = analysis_entry.get("tests")
        if not isinstance(tests, dict):
            tests = {}
            analysis_entry["tests"] = tests

        expected_diff = parse_expected_diff(source_entry)
        if step2_entries is not None:
            actual_diff = step2_entries[i].get("query_difficulty") if isinstance(step2_entries[i], dict) else None
        else:
            actual_diff = analysis_entry.get("query_difficulty")

        if not isinstance(actual_diff, int):
            missing_actual += 1

        tests["test7_difficulty"] = build_test7(expected_diff, actual_diff)

    recompute_summary(analysis_obj)

    after_pass = sum(
        1
        for e in analysis_entries
        if isinstance((e.get("tests") or {}).get("test7_difficulty"), dict)
        and (e.get("tests") or {}).get("test7_difficulty", {}).get("passed") is True
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(analysis_obj, f, ensure_ascii=False, indent=2)

    print(f"Wrote: {output_path}")
    print(f"Entries: {len(analysis_entries)}")
    print(f"test7 pass before: {before_pass}")
    print(f"test7 pass after: {after_pass}")
    print(f"entries without integer actual_diff: {missing_actual}")


if __name__ == "__main__":
    main()
