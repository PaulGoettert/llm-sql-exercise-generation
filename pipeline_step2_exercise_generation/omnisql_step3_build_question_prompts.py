#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


SYSTEM_PROMPT = (
    "Du bist Dozent fuer Datenbanksysteme. "
    "Du formulierst aus einer geprueften SQL-Query eindeutige deutschsprachige "
    "SQL-Uebungs- oder Klausurfragen."
)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_user_prompt(record, num_candidates):
    schema_text = ((record.get("prompt_schema") or {}).get("schema_text") or "").strip()
    sql = (record.get("query_text") or "").strip()
    db_id = record.get("db_id")
    expected_diff = record.get("expected_diff")

    return f"""Du bist Dozent fuer Datenbanksysteme.

Deine Aufgabe ist es, aus einer geprueften SQL-Query mehrere eindeutige deutschsprachige Aufgabenfragen fuer eine SQL-Uebungs- oder Klausuraufgabe zu formulieren.

Die Fragen sollen von Studierenden durch Schreiben einer SQL-Query beantwortet werden koennen.

Datenbank:
{db_id}

Schwierigkeitsstufe:
diff{expected_diff}

Datenbankschema:
{schema_text}

SQL-Query:
{sql}

Anforderungen:
1. Erklaere kurz, was die SQL-Query macht.
2. Formuliere danach genau {num_candidates} unterschiedliche Kandidatenfragen.
3. Jede Kandidatenfrage muss exakt zur SQL-Query passen.
4. Keine Kandidatenfrage darf zusaetzliche Bedingungen einfuehren.
5. Keine Kandidatenfrage darf Bedingungen, Ausgabespalten, Aggregationen, Sortierungen oder Begrenzungen aus der SQL-Query weglassen.
6. Formuliere im Stil einer Uebungs- oder Klausuraufgabe.
7. Bevorzuge Formulierungen wie "Geben Sie ... aus", "Ermitteln Sie ..." oder "Listen Sie ... auf".
8. Verwende keine Markdown-Codebloecke.

Ausgabeformat:
[EXPLANATION-START]
Kurze Erklaerung der SQL-Query.
[EXPLANATION-END]

[CANDIDATES-START]
1. Erste Kandidatenfrage
2. Zweite Kandidatenfrage
...
{num_candidates}. Letzte Kandidatenfrage
[CANDIDATES-END]
"""


def build_prompt_record(record, num_candidates):
    out = dict(record)
    out["question_prompt"] = {
        "method": "omnisql_style_sql_to_question",
        "num_candidates": num_candidates,
        "system": SYSTEM_PROMPT,
        "user": build_user_prompt(record, num_candidates),
        "expected_output_markers": {
            "explanation_start": "[EXPLANATION-START]",
            "explanation_end": "[EXPLANATION-END]",
            "candidates_start": "[CANDIDATES-START]",
            "candidates_end": "[CANDIDATES-END]",
        },
    }
    out["pipeline_state"] = dict(record.get("pipeline_state") or {})
    out["pipeline_state"]["step"] = "omnisql_step3_question_prompt"
    return out


def main():
    parser = argparse.ArgumentParser(
        description="OmniSQL-style step 3: build LLM prompts for SQL-to-question candidate generation."
    )
    parser.add_argument("--input", required=True, help="omnisql_step2 JSON file")
    parser.add_argument("--output", required=True, help="step-3 output JSON file")
    parser.add_argument("--num-candidates", type=int, default=5)
    parser.add_argument("--limit", type=int, help="Optional number of records for a dry run")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    data = load_json(input_path)

    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("input must be a step-2 object with a records list")

    records = data["records"]
    if args.limit is not None:
        records = records[: args.limit]

    output_records = []
    missing_prompt_schema = 0
    missing_sql = 0

    for record in records:
        if not isinstance(record, dict):
            continue
        if not isinstance(record.get("prompt_schema"), dict):
            missing_prompt_schema += 1
            continue
        if not isinstance(record.get("query_text"), str) or not record.get("query_text").strip():
            missing_sql += 1
            continue
        output_records.append(build_prompt_record(record, args.num_candidates))

    result = {
        "dataset_type": "omnisql_step3_question_prompts",
        "source_file": str(input_path),
        "input_records": len(records),
        "output_records": len(output_records),
        "num_candidates": args.num_candidates,
        "missing_prompt_schema": missing_prompt_schema,
        "missing_sql": missing_sql,
        "records": output_records,
    }

    write_json(output_path, result)

    print(f"Input records: {len(records)}")
    print(f"Output records: {len(output_records)}")
    print(f"Missing prompt schema: {missing_prompt_schema}")
    print(f"Missing SQL: {missing_sql}")
    print(f"Candidates per record: {args.num_candidates}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
