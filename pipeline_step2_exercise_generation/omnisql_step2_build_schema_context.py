#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_value(value):
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return repr(value)
    return str(value)


def format_sample_values(values, max_values):
    if not isinstance(values, list) or not values:
        return ""
    selected = values[:max_values]
    return ", ".join(format_value(value) for value in selected)


def format_fk_reference(ref):
    if not isinstance(ref, dict):
        return None
    to_table = ref.get("to_table")
    to_column = ref.get("to_column")
    if not to_table or not to_column:
        return None
    return f"{to_table}.{to_column}"


def build_schema_text(record, max_sample_values):
    metadata = record.get("schema_metadata") or {}
    tables = metadata.get("tables") or {}
    foreign_keys = metadata.get("foreign_keys") or []

    lines = []
    lines.append(f"Database: {record.get('db_id')}")
    lines.append("")
    lines.append("Schema:")

    for table_name, table in tables.items():
        if not isinstance(table, dict):
            continue
        table_label = table.get("technical_label") or table_name
        primary_key = table.get("primary_key") or []
        columns = table.get("columns") or {}

        pk_text = ""
        if primary_key:
            pk_text = f" primary key: {', '.join(primary_key)}"
        lines.append(f"- Table {table_name} ({table_label}){pk_text}")

        for column_name, column in columns.items():
            if not isinstance(column, dict):
                continue
            parts = [f"  - {column_name}: {column.get('type')}"]
            label = column.get("technical_label")
            if label and label != column_name:
                parts.append(f"label: {label}")
            if column.get("is_primary_key") is True:
                parts.append("primary key")

            refs = []
            for ref in column.get("foreign_key_references") or []:
                formatted = format_fk_reference(ref)
                if formatted:
                    refs.append(formatted)
            if refs:
                parts.append(f"foreign key to {', '.join(refs)}")

            sample_values = format_sample_values(column.get("sample_values"), max_sample_values)
            if sample_values:
                parts.append(f"sample values: {sample_values}")

            lines.append("; ".join(parts))

    if foreign_keys:
        lines.append("")
        lines.append("Foreign keys:")
        for fk in foreign_keys:
            raw = fk.get("raw") if isinstance(fk, dict) else None
            if raw:
                lines.append(f"- {raw}")

    return "\n".join(lines)


def build_prompt_schema(record, max_sample_values):
    metadata = record.get("schema_metadata") or {}
    tables = metadata.get("tables") or {}

    prompt_tables = []
    for table_name, table in tables.items():
        if not isinstance(table, dict):
            continue
        columns = []
        for column_name, column in (table.get("columns") or {}).items():
            if not isinstance(column, dict):
                continue
            columns.append(
                {
                    "name": column_name,
                    "type": column.get("type"),
                    "technical_label": column.get("technical_label"),
                    "is_primary_key": column.get("is_primary_key"),
                    "foreign_key_references": column.get("foreign_key_references") or [],
                    "sample_values": (column.get("sample_values") or [])[:max_sample_values],
                }
            )
        prompt_tables.append(
            {
                "name": table_name,
                "technical_label": table.get("technical_label"),
                "primary_key": table.get("primary_key") or [],
                "columns": columns,
            }
        )

    return {
        "db_id": record.get("db_id"),
        "tables": prompt_tables,
        "foreign_keys": metadata.get("foreign_keys") or [],
        "schema_text": build_schema_text(record, max_sample_values),
    }


def main():
    parser = argparse.ArgumentParser(
        description="OmniSQL-style step 2: build compact schema context for later question prompts."
    )
    parser.add_argument("--input", required=True, help="omnisql_step1 JSON file")
    parser.add_argument("--output", required=True, help="step-2 output JSON file")
    parser.add_argument("--limit", type=int, help="Optional number of records for a dry run")
    parser.add_argument("--max-sample-values", type=int, default=3)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    data = load_json(input_path)

    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("input must be a step-1 object with a records list")

    records = data["records"]
    if args.limit is not None:
        records = records[: args.limit]

    output_records = []
    missing_schema_metadata = 0

    for record in records:
        if not isinstance(record, dict):
            continue
        if not isinstance(record.get("schema_metadata"), dict):
            missing_schema_metadata += 1
            continue

        out = dict(record)
        out["prompt_schema"] = build_prompt_schema(record, args.max_sample_values)
        out["pipeline_state"] = dict(record.get("pipeline_state") or {})
        out["pipeline_state"]["step"] = "omnisql_step2_schema_context"
        output_records.append(out)

    result = {
        "dataset_type": "omnisql_step2_schema_context",
        "source_file": str(input_path),
        "input_records": len(records),
        "output_records": len(output_records),
        "missing_schema_metadata": missing_schema_metadata,
        "records": output_records,
    }

    write_json(output_path, result)

    print(f"Input records: {len(records)}")
    print(f"Output records: {len(output_records)}")
    print(f"Missing schema metadata: {missing_schema_metadata}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
