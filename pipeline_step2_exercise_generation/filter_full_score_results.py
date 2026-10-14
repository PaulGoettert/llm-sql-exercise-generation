#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


WEIGHTS = {
    "test1_parse": 3,
    "test2_validate": 5,
    "test3_execution": 12,
    "test5_foreign_keys": 6,
    "test6_lint": 4,
    "test7_difficulty": 6,
    "test4_preview": 1,
}

FULL_SCORE = sum(WEIGHTS.values())


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_rows(data):
    if isinstance(data, dict) and isinstance(data.get("analysis"), list):
        return data["analysis"], data
    if isinstance(data, list):
        return data, None
    raise ValueError("input must be a JSON list or an object with an 'analysis' list")


def test_score(row):
    tests = row.get("tests")
    if not isinstance(tests, dict):
        return 0

    score = 0
    for name, weight in WEIGHTS.items():
        test = tests.get(name)
        if isinstance(test, dict) and test.get("passed") is True:
            score += weight
    return score


def main():
    parser = argparse.ArgumentParser(description="Keep only final result rows with full test score.")
    parser.add_argument("--input", required=True, help="results_with_schema_<run_id>.json")
    parser.add_argument("--output", required=True, help="filtered output JSON")
    parser.add_argument(
        "--keep-wrapper",
        action="store_true",
        help="Preserve an input object wrapper and replace its analysis list.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    data = load_json(input_path)
    rows, wrapper = extract_rows(data)

    kept = []
    score_counts = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        score = test_score(row)
        score_counts[score] = score_counts.get(score, 0) + 1
        if score == FULL_SCORE:
            out = dict(row)
            out["final_score"] = score
            kept.append(out)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.keep_wrapper and wrapper is not None:
        output_data = dict(wrapper)
        output_data["analysis"] = kept
        output_data["full_score_filter"] = {
            "input_file": str(input_path),
            "full_score": FULL_SCORE,
            "input_records": len(rows),
            "kept_records": len(kept),
            "removed_records": len(rows) - len(kept),
            "score_counts": dict(sorted(score_counts.items())),
        }
    else:
        output_data = kept

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Input records: {len(rows)}")
    print(f"Full score: {FULL_SCORE}")
    print(f"Kept records: {len(kept)}")
    print(f"Removed records: {len(rows) - len(kept)}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
