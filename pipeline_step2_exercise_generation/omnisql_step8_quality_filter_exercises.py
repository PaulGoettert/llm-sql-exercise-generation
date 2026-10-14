#!/usr/bin/env python3
import argparse
import json
import re
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


def has_any(text: str, terms) -> bool:
    lowered = str(text or "").casefold()
    return any(term.casefold() in lowered for term in terms)


def has_regex(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, str(text or ""), flags=re.IGNORECASE))


def hard_filter_reasons(record):
    question = record.get("question") or ""
    sql = record.get("sql_query") or ""
    reasons = []

    if has_any(
        question,
        [
            "sql-abfrage",
            "sql-query",
            "gegebenen sql",
            "gegebenen abfrage",
            "wie in der abfrage",
            "abfrage angegeben",
            "sql statement",
            "sql-statement",
        ],
    ):
        reasons.append("self_reference_sql")

    if has_any(question, ["faehren", "fähren"]):
        reasons.append("wrong_translation_ferries")

    if has_any(question, ["schaeden", "schäden"]):
        reasons.append("wrong_translation_damages")

    if has_regex(question, r"\bZiele\b|\bZielen\b") and has_regex(
        sql, r"`Goals`|\.Goals|\bGoals\b"
    ):
        reasons.append("goals_translated_as_targets")

    if has_regex(question, r"\bTore\b") and has_regex(sql, r"`Tries`|\.Tries|\bTries\b"):
        reasons.append("tries_goals_confusion")

    question_requests_sort = has_regex(
        question,
        r"(sortiert|sortieren|aufsteigend|absteigend|alphabetisch|geordnet nach)",
    )
    sql_has_order = has_regex(sql, r"\border\s+by\b")
    question_mentions_sort = has_regex(
        question,
        r"(sortiert|sortieren|aufsteigend|absteigend|geordnet|reihenfolge|alphabetisch|höchste|niedrigste|kleinste|größte|groesste|null)",
    )
    if question_requests_sort and not sql_has_order:
        reasons.append("question_sort_not_in_sql")
    if sql_has_order and not question_mentions_sort:
        reasons.append("sql_order_not_in_question")

    question_requests_limit = has_regex(
        question, r"(top\s*\d+|ersten\s+\d+|erste\s+\d+|nur\s+\d+)"
    )
    sql_has_limit = has_regex(sql, r"\blimit\b")
    question_mentions_limit = has_regex(
        question, r"(top|ersten|erste\s+\d+|nur\s+\d+|begrenz|limit|höchsten|niedrigsten)"
    )
    if question_requests_limit and not sql_has_limit:
        reasons.append("question_limit_not_in_sql")
    if has_regex(sql, r"\blimit\s+\d+") and not question_mentions_limit:
        reasons.append("sql_limit_not_in_question")

    return reasons


def review_reasons(record):
    question = record.get("question") or ""
    sql = record.get("sql_query") or ""
    reasons = []

    if has_any(
        question,
        [
            "select-anweisung",
            "where-bedingung",
            "having-bedingung",
            "group by",
            "order by",
            "union-struktur",
            "union-operator",
            "union-verknüpfung",
            "union-verknuepfung",
        ],
    ):
        reasons.append("raw_sql_terms_in_question")

    if has_any(
        question,
        [
            "inner join",
            "left join",
            "right join",
            "full join",
            "join-operation",
            "inner join-beziehungen",
            "join-beziehungen",
        ],
    ):
        reasons.append("technical_join_wording")

    if has_regex(sql, r"\bdistinct\b") and not has_regex(
        question,
        r"(eindeutig|einzigartig|verschieden|unterschiedlich|distinct|ohne duplikate|einmalig)",
    ):
        reasons.append("distinct_not_explicit_in_question")

    return reasons


def audit_record(record, reasons, severity):
    validation = record.get("validation") or {}
    return {
        "record_id": record.get("record_id"),
        "entry_index": record.get("entry_index"),
        "db_id": record.get("db_id"),
        "expected_diff": record.get("expected_diff"),
        "severity": severity,
        "reasons": reasons,
        "question": record.get("question"),
        "sql_query": record.get("sql_query"),
        "roundtrip_generated_sql": validation.get("roundtrip_generated_sql"),
        "row_count": validation.get("original_row_count"),
        "compare_mode": validation.get("compare_mode"),
        "result_preview": validation.get("original_result_preview"),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Step 8 quality filter for validated exercise records."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--clean-output", required=True, type=Path)
    parser.add_argument("--filtered-output", required=True, type=Path)
    parser.add_argument("--review-output", required=True, type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    data = load_json(args.input)
    records = data.get("records") or []

    clean_records = []
    filtered_records = []
    review_records = []

    for record in records:
        hard_reasons = hard_filter_reasons(record)
        if hard_reasons:
            filtered_records.append(audit_record(record, hard_reasons, "filtered_out"))
            continue

        soft_reasons = review_reasons(record)
        if soft_reasons:
            review_records.append(audit_record(record, soft_reasons, "review_needed"))

        clean_records.append(record)

    hard_counts = Counter(reason for row in filtered_records for reason in row["reasons"])
    review_counts = Counter(reason for row in review_records for reason in row["reasons"])
    now = datetime.now(timezone.utc).isoformat()

    clean_output = {
        "dataset_type": "omnisql_step8_clean_exercises",
        "source_dataset_type": data.get("dataset_type"),
        "source_file": str(args.input),
        "generated_at": now,
        "input_records": len(records),
        "output_records": len(clean_records),
        "filtered_out_records": len(filtered_records),
        "review_needed_records": len(review_records),
        "hard_filter_reason_counts": dict(hard_counts.most_common()),
        "review_reason_counts": dict(review_counts.most_common()),
        "records": clean_records,
    }
    filtered_output = {
        "dataset_type": "omnisql_step8_filtered_out",
        "source_file": str(args.input),
        "generated_at": now,
        "input_records": len(records),
        "output_records": len(filtered_records),
        "reason_counts": dict(hard_counts.most_common()),
        "records": filtered_records,
    }
    review_output = {
        "dataset_type": "omnisql_step8_review_needed",
        "source_file": str(args.input),
        "generated_at": now,
        "input_records": len(records),
        "output_records": len(review_records),
        "reason_counts": dict(review_counts.most_common()),
        "records": review_records,
    }

    write_json(args.clean_output, clean_output)
    write_json(args.filtered_output, filtered_output)
    write_json(args.review_output, review_output)

    print(f"Input records: {len(records)}")
    print(f"Clean records: {len(clean_records)}")
    print(f"Filtered out records: {len(filtered_records)}")
    print(f"Review needed records: {len(review_records)}")
    print(f"Hard filter reasons: {dict(hard_counts.most_common())}")
    print(f"Review reasons: {dict(review_counts.most_common())}")
    print(f"Clean output: {args.clean_output}")
    print(f"Filtered output: {args.filtered_output}")
    print(f"Review output: {args.review_output}")


if __name__ == "__main__":
    main()
