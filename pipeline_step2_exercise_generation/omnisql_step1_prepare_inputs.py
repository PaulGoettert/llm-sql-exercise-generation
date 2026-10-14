#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


FULL_SCORE = 37


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def split_identifier(name):
    if not isinstance(name, str):
        return []
    parts = re.split(r"[_\s]+", name.strip())
    tokens = []
    for part in parts:
        if not part:
            continue
        # Split simple CamelCase without trying to infer domain semantics.
        tokens.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", part))
    return [t.lower() for t in tokens if t]


def technical_label(identifier):
    tokens = split_identifier(identifier)
    if not tokens:
        return str(identifier)
    return " ".join(tokens)


def parse_foreign_key(fk):
    if not isinstance(fk, str):
        return None
    if "=" not in fk:
        return None
    left, right = [part.strip() for part in fk.split("=", 1)]
    if "." not in left or "." not in right:
        return None
    left_table, left_column = [part.strip(" `\"") for part in left.split(".", 1)]
    right_table, right_column = [part.strip(" `\"") for part in right.split(".", 1)]
    return {
        "from_table": left_table,
        "from_column": left_column,
        "to_table": right_table,
        "to_column": right_column,
        "raw": fk,
    }


def sample_values_for_column(sample_rows, table, column, max_values):
    rows = sample_rows.get(table)
    if not isinstance(rows, list):
        return []

    values = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or column not in row:
            continue
        value = row.get(column)
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        values.append(value)
        if len(values) >= max_values:
            break
    return values


def build_schema_metadata(row, max_sample_values):
    column_types = row.get("column_types") or {}
    primary_keys = row.get("primary_keys") or {}
    foreign_keys = row.get("foreign_keys") or []
    sample_rows = row.get("sample_rows") or {}

    if not isinstance(column_types, dict):
        column_types = {}
    if not isinstance(primary_keys, dict):
        primary_keys = {}
    if not isinstance(foreign_keys, list):
        foreign_keys = []
    if not isinstance(sample_rows, dict):
        sample_rows = {}

    parsed_foreign_keys = []
    outgoing = {}
    incoming = {}
    for fk in foreign_keys:
        parsed = parse_foreign_key(fk)
        if not parsed:
            continue
        parsed_foreign_keys.append(parsed)
        outgoing.setdefault((parsed["from_table"], parsed["from_column"]), []).append(parsed)
        incoming.setdefault((parsed["to_table"], parsed["to_column"]), []).append(parsed)

    tables = {}
    for table_name, columns in column_types.items():
        if not isinstance(columns, dict):
            continue
        pk_cols = primary_keys.get(table_name) or []
        if not isinstance(pk_cols, list):
            pk_cols = []

        table_columns = {}
        for column_name, column_type in columns.items():
            key = (table_name, column_name)
            table_columns[column_name] = {
                "type": column_type,
                "technical_label": technical_label(column_name),
                "is_primary_key": column_name in pk_cols,
                "foreign_key_references": outgoing.get(key, []),
                "referenced_by": incoming.get(key, []),
                "sample_values": sample_values_for_column(
                    sample_rows, table_name, column_name, max_sample_values
                ),
            }

        tables[table_name] = {
            "technical_label": technical_label(table_name),
            "primary_key": pk_cols,
            "columns": table_columns,
            "sample_rows": sample_rows.get(table_name, []),
        }

    return {
        "tables": tables,
        "foreign_keys": parsed_foreign_keys,
        "raw_foreign_keys": foreign_keys,
        "metadata_source": {
            "column_types": "input.column_types",
            "primary_keys": "input.primary_keys",
            "foreign_keys": "input.foreign_keys",
            "sample_rows": "input.sample_rows",
        },
    }


def tests_all_passed(row):
    tests = row.get("tests")
    if not isinstance(tests, dict):
        return False
    return all(isinstance(test, dict) and test.get("passed") is True for test in tests.values())


def build_prepared_record(row, max_sample_values):
    return {
        "record_id": row.get("record_id"),
        "entry_index": row.get("entry_index"),
        "db_id": row.get("db_id"),
        "expected_diff": row.get("expected_diff"),
        "query_text": row.get("query_text"),
        "tests": row.get("tests"),
        "final_score": row.get("final_score"),
        "schema_metadata": build_schema_metadata(row, max_sample_values),
        "source_metadata": {
            "model2_action": row.get("model2_action"),
        },
        "pipeline_state": {
            "step": "omnisql_step1_schema_metadata",
            "optional_sql_structure_analysis": False,
            "optional_canonical_verbalization": False,
            "optional_component_check": False,
            "optional_roundtrip_validation": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="OmniSQL-style step 1: load verified SQL records and extract reliable schema metadata."
    )
    parser.add_argument("--input", required=True, help="Full-score results_with_schema JSON file")
    parser.add_argument("--output", required=True, help="Prepared step-1 output JSON file")
    parser.add_argument("--limit", type=int, help="Optional number of records for a dry run")
    parser.add_argument("--max-sample-values", type=int, default=3)
    parser.add_argument("--require-full-score", action="store_true", default=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    rows = load_json(input_path)
    if not isinstance(rows, list):
        raise ValueError("input must be a JSON list")

    if args.limit is not None:
        rows = rows[: args.limit]

    prepared = []
    skipped_not_full_score = 0
    skipped_failed_tests = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        if args.require_full_score and row.get("final_score") != FULL_SCORE:
            skipped_not_full_score += 1
            continue
        if not tests_all_passed(row):
            skipped_failed_tests += 1
            continue
        prepared.append(build_prepared_record(row, args.max_sample_values))

    result = {
        "dataset_type": "omnisql_step1_schema_metadata",
        "source_file": str(input_path),
        "input_records": len(rows),
        "output_records": len(prepared),
        "skipped_not_full_score": skipped_not_full_score,
        "skipped_failed_tests": skipped_failed_tests,
        "records": prepared,
    }

    write_json(output_path, result)

    print(f"Input records: {len(rows)}")
    print(f"Output records: {len(prepared)}")
    print(f"Skipped not full score: {skipped_not_full_score}")
    print(f"Skipped failed tests: {skipped_failed_tests}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()

