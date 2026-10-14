import argparse
import json
from collections import Counter
from pathlib import Path


DEFAULT_TEST_SEQUENCE = [
    "test1_parse",
    "test2_validate",
    "test3_execution",
    "test4_preview",
    "test5_foreign_keys",
    "test6_lint",
    "test7_difficulty",
]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def pick_test_sequence(files_data):
    for _, data in files_data:
        if isinstance(data, dict):
            summary = data.get("summary")
            if isinstance(summary, dict):
                seq = summary.get("test_sequence")
                if isinstance(seq, list) and seq:
                    return seq
    return DEFAULT_TEST_SEQUENCE


def build_summary(analysis, test_sequence):
    total = len(analysis)
    per_test_pass_counts = {}
    for test in test_sequence:
        per_test_pass_counts[test] = sum(
            1
            for entry in analysis
            if isinstance(entry, dict)
            and isinstance(entry.get("tests"), dict)
            and isinstance(entry["tests"].get(test), dict)
            and entry["tests"][test].get("passed") is True
        )

    combination_counter = Counter(
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

    combination_details = []
    for pattern, count in combination_counter.most_common():
        combination_details.append(
            {
                "pattern": {test: flag for test, flag in zip(test_sequence, pattern)},
                "count": count,
                "share": (count / total) if total else 0.0,
            }
        )

    return {
        "test_sequence": test_sequence,
        "per_test_pass_counts": per_test_pass_counts,
        "combination_details": combination_details,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Combine all *_after_lint.json files chronologically and rebuild a global summary."
        )
    )
    parser.add_argument(
        "--input-dir",
        default=str(pathlib.Path(__file__).resolve().parent / "analyse_feedback"),
        help="Directory with *_after_lint.json files",
    )
    parser.add_argument(
        "--output",
        default=str(pathlib.Path(__file__).resolve().parent / "analyse_feedback" / "step2_output_combined_chronological_after_lint.json"),
        help="Output combined JSON path",
    )
    parser.add_argument(
        "--sort-by",
        choices=["mtime", "name"],
        default="mtime",
        help="Chronological sort by file modification time or by filename",
    )
    parser.add_argument(
        "--exclude-output",
        action="store_true",
        help="Exclude output file itself from input scan (recommended for reruns)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)

    if not input_dir.exists():
        raise FileNotFoundError(f"input dir not found: {input_dir}")

    files = [p for p in input_dir.glob("*_after_lint.json") if p.is_file()]
    if args.exclude_output:
        files = [p for p in files if p.resolve() != output_path.resolve()]
    if not files:
        raise ValueError("no *_after_lint.json files found")

    if args.sort_by == "mtime":
        files.sort(key=lambda p: (p.stat().st_mtime, p.name))
    else:
        files.sort(key=lambda p: p.name)

    files_data = [(path, load_json(path)) for path in files]
    test_sequence = pick_test_sequence(files_data)

    combined_analysis = []
    for path, data in files_data:
        if not isinstance(data, dict):
            raise ValueError(f"{path} must be an object with 'analysis'")
        analysis = data.get("analysis")
        if not isinstance(analysis, list):
            raise ValueError(f"{path} missing list field 'analysis'")
        for item in analysis:
            if isinstance(item, dict):
                row = dict(item)
                row["_combined_from_file"] = path.name
                combined_analysis.append(row)
            else:
                combined_analysis.append(item)

    summary = build_summary(combined_analysis, test_sequence)
    output = {
        "source_file": output_path.name,
        "combined_files_in_order": [p.name for p in files],
        "total_entries": len(combined_analysis),
        "analysis": combined_analysis,
        "summary": summary,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Combined files: {len(files)}")
    print(f"Total entries: {len(combined_analysis)}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
