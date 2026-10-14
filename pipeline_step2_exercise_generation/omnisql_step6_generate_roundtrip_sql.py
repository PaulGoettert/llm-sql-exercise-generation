#!/usr/bin/env python3
import argparse
import json
import re
import time
from pathlib import Path

import requests


SQL_PATTERN = re.compile(r"\[SQL-START\](.*?)\[SQL-END\]", re.IGNORECASE | re.DOTALL)


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
    sql = re.sub(r"^```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"```$", "", sql).strip()
    sql = sql.rstrip(";").strip()
    return re.sub(r"\s+", " ", sql)


def parse_sql(text: str) -> str:
    text = str(text or "").strip()
    match = SQL_PATTERN.search(text)
    if match:
        return normalize_sql(match.group(1))

    fenced = re.search(r"```(?:sql)?(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return normalize_sql(fenced.group(1))

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sql_lines = []
    in_sql = False
    for line in lines:
        if re.match(r"^(SELECT|WITH)\b", line, flags=re.IGNORECASE):
            in_sql = True
        if in_sql:
            sql_lines.append(line)

    return normalize_sql(" ".join(sql_lines) if sql_lines else text)


def is_plausible_sql(sql: str) -> bool:
    if not sql:
        return False
    if not re.match(r"^(SELECT|WITH)\b", sql, flags=re.IGNORECASE):
        return False
    forbidden = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE")
    return not any(re.search(rf"\b{word}\b", sql, flags=re.IGNORECASE) for word in forbidden)


def selected_question(record) -> str:
    selection = record.get("question_selection") or {}
    question = selection.get("selected_question")
    return " ".join(str(question or "").strip().split())


def schema_text(record) -> str:
    prompt_schema = record.get("prompt_schema") or {}
    text = prompt_schema.get("schema_text")
    if text:
        return str(text).strip()

    schema_metadata = record.get("schema_metadata") or {}
    if schema_metadata:
        return json.dumps(schema_metadata, ensure_ascii=False, indent=2)
    return ""


def build_prompt(record):
    question = selected_question(record)
    schema = schema_text(record)
    db_id = record.get("db_id") or ""

    system_prompt = (
        "Du bist ein Text-to-SQL-System. Du erzeugst aus einer deutschen Frage und "
        "einem Datenbankschema genau eine syntaktisch gueltige SQLite-SELECT-Query."
    )
    user_prompt = f"""Erzeuge eine SQL-Query fuer die folgende Frage.

Regeln:
- Verwende ausschliesslich Tabellen und Spalten aus dem Schema.
- Erzeuge genau eine SQLite-SELECT-Query.
- Erzeuge keine Erklaerung und keinen Markdown-Codeblock.
- Fuehre keine zusaetzlichen Bedingungen ein, die nicht in der Frage stehen.
- Lasse keine in der Frage genannten Ausgabespalten, Filter, Joins, Aggregationen, Gruppierungen oder Sortierungen weg.
- Wenn Joins noetig sind, nutze die Foreign Keys aus dem Schema.
- Gib die SQL-Query exakt zwischen den Markern aus.

Datenbank:
{db_id}

Schema:
{schema}

Frage:
{question}

Ausgabeformat:
[SQL-START]
SELECT ...
[SQL-END]
"""
    return system_prompt, user_prompt


def call_ollama(url, model, system_prompt, user_prompt, temperature, top_p, num_predict, timeout):
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": num_predict,
        },
    }
    response = requests.post(url, json=payload, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {response.status_code}: {response.text[:1000]}")
    data = response.json()
    message = data.get("message") or {}
    return (message.get("content") or data.get("response") or "").strip()


def has_completed_sql(record) -> bool:
    generation = record.get("roundtrip_sql_generation")
    if not isinstance(generation, dict):
        return False
    return generation.get("status") == "ok" and bool(generation.get("generated_sql"))


def existing_records_by_id(output_path: Path):
    if not output_path.exists():
        return {}
    data = load_json(output_path)
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return {}
    return {
        row.get("record_id"): row
        for row in records
        if isinstance(row, dict) and isinstance(row.get("record_id"), str) and has_completed_sql(row)
    }


def generate_sql_for_record(args, record):
    system_prompt, user_prompt = build_prompt(record)
    last_error = None
    last_raw_output = ""

    for attempt in range(1, args.max_retries + 1):
        try:
            raw_output = call_ollama(
                args.url,
                args.model,
                system_prompt,
                user_prompt,
                args.temperature,
                args.top_p,
                args.num_predict,
                args.timeout,
            )
            last_raw_output = raw_output
            sql = parse_sql(raw_output)
            if is_plausible_sql(sql):
                return {
                    "method": "question_schema_to_sql",
                    "model": args.model,
                    "status": "ok",
                    "selected_question": selected_question(record),
                    "generated_sql": sql,
                    "raw_output": raw_output,
                    "attempts": attempt,
                    "error": None,
                }
            last_error = f"no_plausible_select_sql: {sql[:300]}"
        except Exception as exc:
            last_error = str(exc)

        if attempt < args.max_retries:
            time.sleep(args.retry_sleep)

    return {
        "method": "question_schema_to_sql",
        "model": args.model,
        "status": "failed",
        "selected_question": selected_question(record),
        "generated_sql": "",
        "raw_output": last_raw_output,
        "attempts": args.max_retries,
        "error": last_error or "unknown_error",
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="OmniSQL-style step 6: regenerate SQL from selected question and schema."
    )
    parser.add_argument("--input", required=True, help="omnisql_step5 JSON file")
    parser.add_argument("--output", required=True, help="step-6 output JSON file")
    parser.add_argument("--model", required=True, help="Ollama model name")
    parser.add_argument("--url", default="http://localhost:11434/api/chat")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--num-predict", type=int, default=700)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--limit", type=int, help="Optional number of records for a test run")
    parser.add_argument("--resume", action="store_true", help="Reuse already generated records in output")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    data = load_json(input_path)

    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("input must be a step-5 object with a records list")

    records = data["records"]
    if args.limit is not None:
        records = records[: args.limit]

    completed = existing_records_by_id(output_path) if args.resume else {}
    output_records = []
    generated = 0
    reused = 0
    failed = 0

    for index, record in enumerate(records, start=1):
        record_id = record.get("record_id")
        if args.resume and record_id in completed:
            output_records.append(completed[record_id])
            reused += 1
            continue

        out = dict(record)
        generation = generate_sql_for_record(args, record)
        out["roundtrip_sql_generation"] = generation
        out["pipeline_state"] = dict(record.get("pipeline_state") or {})
        out["pipeline_state"]["step"] = "omnisql_step6_roundtrip_sql_generated"

        if generation["status"] == "ok":
            generated += 1
        else:
            failed += 1

        output_records.append(out)

        if index % 25 == 0 or index == len(records):
            result = {
                "dataset_type": "omnisql_step6_roundtrip_sql",
                "source_dataset_type": data.get("dataset_type"),
                "source_file": str(input_path),
                "model": args.model,
                "input_records": len(records),
                "output_records": len(output_records),
                "generated_records": generated,
                "reused_records": reused,
                "failed_records": failed,
                "records": output_records,
            }
            write_json(output_path, result)
            print(f"[{index}/{len(records)}] generated={generated} reused={reused} failed={failed}")

    result = {
        "dataset_type": "omnisql_step6_roundtrip_sql",
        "source_dataset_type": data.get("dataset_type"),
        "source_file": str(input_path),
        "model": args.model,
        "input_records": len(records),
        "output_records": len(output_records),
        "generated_records": generated,
        "reused_records": reused,
        "failed_records": failed,
        "records": output_records,
    }
    write_json(output_path, result)

    print(f"Input records: {len(records)}")
    print(f"Output records: {len(output_records)}")
    print(f"Generated records: {generated}")
    print(f"Reused records: {reused}")
    print(f"Failed records: {failed}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()

