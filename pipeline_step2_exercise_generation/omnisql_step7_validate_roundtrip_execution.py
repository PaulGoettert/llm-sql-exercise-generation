#!/usr/bin/env python3
import argparse
import json
import hashlib
import re
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalize_sql(sql: str) -> str:
    sql = str(sql or "").strip()
    match = re.search(r"\[SQL-START\](.*?)\[SQL-END\]", sql, flags=re.IGNORECASE | re.DOTALL)
    if match:
        sql = match.group(1).strip()
    sql = re.sub(r"\[SQL-START\]", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"\[SQL-END\]", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"^```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"```$", "", sql).strip()
    return sql.rstrip(";").strip()


def contains_order_by(sql: str) -> bool:
    return bool(re.search(r"\border\s+by\b", sql or "", flags=re.IGNORECASE))


def db_path_for(db_root: Path, db_id: str) -> Path:
    return db_root / db_id / f"{db_id}.sqlite"


def normalize_value(value):
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float):
        value = round(value, 12)
        if value.is_integer():
            return int(value)
        return value
    return value


def normalize_rows(rows):
    return [tuple(normalize_value(value) for value in row) for row in rows]


def comparable_rows(rows, ordered: bool):
    normalized = normalize_rows(rows)
    if ordered:
        return normalized
    return Counter(normalized)


def comparable_to_jsonable(comparable):
    if isinstance(comparable, Counter):
        items = [
            {"row": list(row), "count": count}
            for row, count in sorted(comparable.items(), key=lambda item: repr(item[0]))
        ]
        return {"mode": "unordered_multiset", "rows": items}
    return {"mode": "ordered", "rows": [list(row) for row in comparable]}


def result_hash(comparable) -> str:
    payload = json.dumps(comparable_to_jsonable(comparable), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def result_preview(rows, limit: int):
    return [list(row) for row in normalize_rows(rows[:limit])]


def execute_query(db_path: Path, sql: str, timeout_seconds: float, max_rows: int):
    sql = normalize_sql(sql)
    if not sql:
        raise ValueError("empty sql")
    if not re.match(r"^(select|with)\b", sql, flags=re.IGNORECASE):
        raise ValueError("only SELECT/WITH queries are allowed")

    con = sqlite3.connect(str(db_path), timeout=timeout_seconds)
    con.row_factory = None
    started_at = time.monotonic()

    def progress_handler():
        if time.monotonic() - started_at > timeout_seconds:
            raise TimeoutError(f"query exceeded timeout: {timeout_seconds}s")
        return 0

    # sqlite3 has no hard wall-clock timeout for a single statement. The progress
    # handler checks elapsed time without aborting normal long-but-valid queries.
    con.set_progress_handler(progress_handler, 100_000)
    try:
        cur = con.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        columns = [item[0] for item in cur.description or []]
        if len(rows) > max_rows:
            raise ValueError(f"query returned too many rows: {len(rows)} > {max_rows}")
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }
    finally:
        con.close()


def selected_question(record) -> str:
    selection = record.get("question_selection") or {}
    generation = record.get("roundtrip_sql_generation") or {}
    return str(selection.get("selected_question") or generation.get("selected_question") or "").strip()


def schema_text(record) -> str:
    prompt_schema = record.get("prompt_schema") or {}
    if prompt_schema.get("schema_text"):
        return str(prompt_schema["schema_text"]).strip()
    schema_metadata = record.get("schema_metadata") or {}
    return json.dumps(schema_metadata, ensure_ascii=False, indent=2) if schema_metadata else ""


def build_exercise_record(record, validation):
    return {
        "record_id": record.get("record_id"),
        "entry_index": record.get("entry_index"),
        "db_id": record.get("db_id"),
        "expected_diff": record.get("expected_diff"),
        "db_schema": schema_text(record),
        "question": selected_question(record),
        "sql_query": normalize_sql(record.get("query_text")),
        "validation": validation,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate generated questions by executing original SQL and question-regenerated SQL on the same SQLite DB."
    )
    parser.add_argument("--input", required=True, type=Path, help="omnisql_step6 JSON file")
    parser.add_argument("--output", required=True, type=Path, help="validated exercise output JSON file")
    parser.add_argument(
        "--db-root",
        required=True,
        type=Path,
        help="Spider database root, e.g. /path/to/spider/database",
    )
    parser.add_argument(
        "--skip-db",
        action="append",
        default=[],
        help="db_id to skip. Can be passed multiple times. Use this for empty DBs such as music_2.",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--max-rows", type=int, default=100000)
    parser.add_argument("--result-preview-rows", type=int, default=5)
    parser.add_argument(
        "--compare-mode",
        choices=["auto", "ordered", "unordered"],
        default="auto",
        help="auto keeps order only if either query contains ORDER BY; otherwise compares as multisets.",
    )
    parser.add_argument("--limit", type=int, help="Optional number of records for a test run")
    return parser.parse_args()


def main():
    args = parse_args()
    data = load_json(args.input)
    records = data.get("records") or []
    if args.limit is not None:
        records = records[: args.limit]

    skip_dbs = set(args.skip_db or [])
    valid_exercises = []
    failed_records = []
    skipped_records = []
    stats = {
        "input_records": len(records),
        "validated_records": 0,
        "mismatch_records": 0,
        "execution_error_records": 0,
        "empty_result_records": 0,
        "skipped_records": 0,
    }

    for index, record in enumerate(records, start=1):
        db_id = record.get("db_id")
        record_id = record.get("record_id")
        if db_id in skip_dbs:
            skipped_records.append(
                {"record_id": record_id, "db_id": db_id, "reason": "skipped_db"}
            )
            stats["skipped_records"] += 1
            continue

        original_sql = normalize_sql(record.get("query_text"))
        generated_sql = normalize_sql(
            (record.get("roundtrip_sql_generation") or {}).get("generated_sql")
        )
        db_path = db_path_for(args.db_root, db_id)

        if not db_path.exists():
            failed_records.append(
                {
                    "record_id": record_id,
                    "db_id": db_id,
                    "status": "execution_error",
                    "error": f"db file not found: {db_path}",
                }
            )
            stats["execution_error_records"] += 1
            continue

        try:
            original_result = execute_query(db_path, original_sql, args.timeout, args.max_rows)
            generated_result = execute_query(db_path, generated_sql, args.timeout, args.max_rows)
            if args.compare_mode == "ordered":
                ordered = True
            elif args.compare_mode == "unordered":
                ordered = False
            else:
                ordered = contains_order_by(original_sql) or contains_order_by(generated_sql)

            original_comparable = comparable_rows(original_result["rows"], ordered)
            generated_comparable = comparable_rows(generated_result["rows"], ordered)
            original_hash = result_hash(original_comparable)
            generated_hash = result_hash(generated_comparable)
            same_output = original_comparable == generated_comparable
            validation = {
                "status": "ok" if same_output else "mismatch",
                "method": "sqlite_execution_result_comparison",
                "db_path": str(db_path),
                "compare_mode": "ordered" if ordered else "unordered_multiset",
                "same_result": same_output,
                "result_match_proof": {
                    "original_result_hash": original_hash,
                    "generated_result_hash": generated_hash,
                    "hashes_equal": original_hash == generated_hash,
                    "row_counts_equal": original_result["row_count"] == generated_result["row_count"],
                    "compared_full_result_sets": True,
                },
                "original_row_count": original_result["row_count"],
                "generated_row_count": generated_result["row_count"],
                "original_columns": original_result["columns"],
                "generated_columns": generated_result["columns"],
                "original_result_preview": result_preview(original_result["rows"], args.result_preview_rows),
                "generated_result_preview": result_preview(generated_result["rows"], args.result_preview_rows),
                "result_preview_rows": args.result_preview_rows,
                "roundtrip_generated_sql": generated_sql,
            }

            empty_result = (
                same_output
                and original_result["row_count"] == 0
                and generated_result["row_count"] == 0
            )

            if same_output and not empty_result:
                valid_exercises.append(build_exercise_record(record, validation))
                stats["validated_records"] += 1
            elif empty_result:
                validation["status"] = "empty_result"
                validation["accepted_as_exercise"] = False
                failed_records.append(
                    {
                        "record_id": record_id,
                        "db_id": db_id,
                        "status": "empty_result",
                        "question": selected_question(record),
                        "original_sql": original_sql,
                        "roundtrip_generated_sql": generated_sql,
                        "original_row_count": original_result["row_count"],
                        "generated_row_count": generated_result["row_count"],
                        "original_columns": original_result["columns"],
                        "generated_columns": generated_result["columns"],
                        "original_result_hash": original_hash,
                        "generated_result_hash": generated_hash,
                        "compare_mode": validation["compare_mode"],
                        "reason": "both queries returned an empty result set",
                    }
                )
                stats["empty_result_records"] += 1
            else:
                failed_records.append(
                    {
                        "record_id": record_id,
                        "db_id": db_id,
                        "status": "mismatch",
                        "question": selected_question(record),
                        "original_sql": original_sql,
                        "roundtrip_generated_sql": generated_sql,
                        "original_row_count": original_result["row_count"],
                        "generated_row_count": generated_result["row_count"],
                        "original_columns": original_result["columns"],
                        "generated_columns": generated_result["columns"],
                        "original_result_hash": original_hash,
                        "generated_result_hash": generated_hash,
                        "original_result_preview": validation["original_result_preview"],
                        "generated_result_preview": validation["generated_result_preview"],
                        "compare_mode": validation["compare_mode"],
                    }
                )
                stats["mismatch_records"] += 1
        except Exception as exc:
            failed_records.append(
                {
                    "record_id": record_id,
                    "db_id": db_id,
                    "status": "execution_error",
                    "question": selected_question(record),
                    "original_sql": original_sql,
                    "roundtrip_generated_sql": generated_sql,
                    "error": str(exc),
                }
            )
            stats["execution_error_records"] += 1

        if index % 250 == 0 or index == len(records):
            print(
                f"[{index}/{len(records)}] valid={stats['validated_records']} "
                f"mismatch={stats['mismatch_records']} errors={stats['execution_error_records']} "
                f"empty={stats['empty_result_records']} skipped={stats['skipped_records']}"
            )

    output = {
        "dataset_type": "omnisql_step7_validated_exercises",
        "source_dataset_type": data.get("dataset_type"),
        "source_file": str(args.input),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_root": str(args.db_root),
        "skip_db": sorted(skip_dbs),
        **stats,
        "output_records": len(valid_exercises),
        "records": valid_exercises,
        "failed_records": failed_records,
        "skipped_records_detail": skipped_records,
    }
    write_json(args.output, output)

    print(f"Input records: {stats['input_records']}")
    print(f"Validated records: {stats['validated_records']}")
    print(f"Mismatch records: {stats['mismatch_records']}")
    print(f"Execution error records: {stats['execution_error_records']}")
    print(f"Empty result records: {stats['empty_result_records']}")
    print(f"Skipped records: {stats['skipped_records']}")
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()



