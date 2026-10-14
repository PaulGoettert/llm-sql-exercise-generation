#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

SCHEMA_FIELDS = ("column_types", "primary_keys", "foreign_keys", "sample_rows")
MODEL_FIELDS = (
    "model2_action",
    "expected_diff",
)

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def extract_analysis_rows(data):
    if isinstance(data, dict) and isinstance(data.get("analysis"), list):
        return data["analysis"], data
    if isinstance(data, list):
        return data, None
    raise ValueError("analysis input must be a JSON list or an object with an 'analysis' list")

def build_by_record_id(rows):
    out = {}
    for i, row in enumerate(rows):
        rid = row.get("record_id") if isinstance(row, dict) else None
        if isinstance(rid, str) and rid.strip():
            if rid in out:
                raise ValueError(f"duplicate record_id in merged file: {rid}")
            out[rid] = row
    return out

def main():
    parser = argparse.ArgumentParser(
        description="Join Step2 analysis results with schema/model fields from merged model2 records."
    )
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--merged", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--keep-analysis-wrapper", action="store_true")
    args = parser.parse_args()

    analysis_path = Path(args.analysis)
    merged_path = Path(args.merged)
    output_path = Path(args.output)

    analysis_data = load_json(analysis_path)
    merged_rows = load_json(merged_path)

    if not isinstance(merged_rows, list):
        raise ValueError("merged input must be a JSON list")

    analysis_rows, wrapper = extract_analysis_rows(analysis_data)
    merged_by_id = build_by_record_id(merged_rows)

    joined = []
    missing = []
    joined_by_record_id = 0
    joined_by_position = 0

    for i, analysis_row in enumerate(analysis_rows):
        if not isinstance(analysis_row, dict):
            continue

        record_id = analysis_row.get("record_id")
        merged_row = None

        if isinstance(record_id, str) and record_id.strip():
            merged_row = merged_by_id.get(record_id)
            if merged_row is not None:
                joined_by_record_id += 1

        if merged_row is None:
            entry_index = analysis_row.get("entry_index")
            if isinstance(entry_index, int) and 0 <= entry_index < len(merged_rows):
                merged_row = merged_rows[entry_index]
                joined_by_position += 1
            elif i < len(merged_rows):
                merged_row = merged_rows[i]
                joined_by_position += 1

        if merged_row is None:
            missing.append(record_id or f"analysis_index_{i}")
            continue

        out = dict(analysis_row)
        out["record_id"] = merged_row.get("record_id")

        for field in MODEL_FIELDS:
            if field in merged_row:
                out[field] = merged_row.get(field)

        for field in SCHEMA_FIELDS:
            out[field] = merged_row.get(field)

        joined.append(out)

    if missing:
        raise ValueError(f"{len(missing)} analysis rows could not be joined. First: {missing[:10]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.keep_analysis_wrapper and wrapper is not None:
        output_data = dict(wrapper)
        output_data["analysis"] = joined
        output_data["schema_join"] = {
            "analysis_file": str(analysis_path),
            "merged_file": str(merged_path),
            "records": len(joined),
            "joined_by_record_id": joined_by_record_id,
            "joined_by_position": joined_by_position,
        }
    else:
        output_data = joined

    output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Analysis records: {len(analysis_rows)}")
    print(f"Merged records: {len(merged_rows)}")
    print(f"Joined records: {len(joined)}")
    print(f"Joined by record_id: {joined_by_record_id}")
    print(f"Joined by position: {joined_by_position}")
    print(f"Wrote: {output_path}")

if __name__ == "__main__":
    main()
