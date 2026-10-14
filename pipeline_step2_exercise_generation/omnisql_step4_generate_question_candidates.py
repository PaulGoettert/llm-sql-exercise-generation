#!/usr/bin/env python3
import argparse
import json
import re
import time
from pathlib import Path

import requests


EXPLANATION_PATTERN = re.compile(
    r"\[EXPLANATION-START\](.*?)\[EXPLANATION-END\]",
    flags=re.IGNORECASE | re.DOTALL,
)
QUESTION_PATTERN = re.compile(
    r"\[QUESTION-START\](.*?)\[QUESTION-END\]",
    flags=re.IGNORECASE | re.DOTALL,
)
CANDIDATES_PATTERN = re.compile(
    r"\[CANDIDATES-START\](.*?)\[CANDIDATES-END\]",
    flags=re.IGNORECASE | re.DOTALL,
)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_question(text):
    if not isinstance(text, str):
        return ""
    text = text.strip().strip('"')
    text = re.sub(r"^\s*(?:[-*]\s*)?(?:\d+|[A-Z])[.)]\s*", "", text).strip()
    return re.sub(r"\s+", " ", text)


def parse_candidates_block(text):
    candidates = []
    if not isinstance(text, str):
        return candidates

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    current = None

    for line in lines:
        match = re.match(r"^(?:[-*]\s*)?(\d+|[A-Z])[.)]\s*(.+)$", line)
        if match:
            if current:
                candidates.append(current.strip())
            current = match.group(2).strip()
        elif current:
            current += " " + line
        else:
            candidates.append(line)

    if current:
        candidates.append(current.strip())

    cleaned = []
    seen = set()
    for candidate in candidates:
        candidate = clean_question(candidate)
        if not candidate:
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(candidate)
    return cleaned


def parse_single_llm_output(text):
    if not isinstance(text, str):
        text = ""

    explanation_match = EXPLANATION_PATTERN.search(text)
    question_match = QUESTION_PATTERN.search(text)
    candidates_match = CANDIDATES_PATTERN.search(text)

    explanation = explanation_match.group(1).strip() if explanation_match else ""

    question = ""
    if question_match:
        question = clean_question(question_match.group(1))
    elif candidates_match:
        candidates = parse_candidates_block(candidates_match.group(1))
        question = candidates[0] if candidates else ""
    else:
        candidates = parse_candidates_block(text)
        question = candidates[0] if candidates else clean_question(text)

    return {
        "explanation": explanation,
        "question": question,
        "parse_status": "ok" if question else "no_question_found",
    }


def build_single_candidate_prompt(base_prompt, candidate_number, total_candidates, previous_questions):
    previous_block = ""
    if previous_questions:
        previous_lines = "\n".join(
            f"- {question}" for question in previous_questions if question.strip()
        )
        previous_block = f"""

Bereits erzeugte Kandidatenfragen, die nicht wortgleich wiederholt werden sollen:
{previous_lines}
"""

    return f"""{base_prompt}

WICHTIGE AENDERUNG FUER DIESEN AUFRUF:
Erzeuge jetzt nur Kandidat {candidate_number} von {total_candidates}.
Gib genau eine Kandidatenfrage aus, nicht mehrere.
Die Frage soll semantisch exakt zur SQL-Query passen, aber sprachlich nicht identisch zu vorherigen Kandidaten sein.

Strenge Regeln:
- Erwaehne alle SELECT-Ausgabespalten der SQL-Query.
- Erwaehne alle WHERE-Bedingungen exakt mit Operator und Wert.
- Fuehre keine neuen Bedingungen, Werte, Sortierungen, Gruppierungen oder Begrenzungen ein.
- Verwende keine Beispielwerte aus dem Schema als Filterbedingung, ausser sie stehen direkt in der SQL-Query.
- Wenn eine Spalte technisch benannt ist, darfst du den technischen Spaltennamen verwenden, statt eine unsichere Bedeutung zu erfinden.
- Gib wirklich nur eine Frage aus.{previous_block}

Ausgabeformat fuer diesen einzelnen Aufruf:
[EXPLANATION-START]
Kurze Erklaerung der SQL-Query.
[EXPLANATION-END]

[QUESTION-START]
Eine einzelne Kandidatenfrage.
[QUESTION-END]
"""


def call_ollama(url, model, system_prompt, user_prompt, temperature, top_p, num_predict, timeout):
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt or ""},
            {"role": "user", "content": user_prompt or ""},
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


def has_enough_candidates(row, required_count):
    if not isinstance(row, dict):
        return False
    generation = row.get("question_generation")
    if not isinstance(generation, dict):
        return False
    if generation.get("status") != "ok":
        return False
    candidates = generation.get("candidates")
    if not isinstance(candidates, list):
        return False
    valid_questions = [
        c.get("question")
        for c in candidates
        if isinstance(c, dict) and isinstance(c.get("question"), str) and c.get("question").strip()
    ]
    return len(valid_questions) >= required_count


def existing_records_by_id(output_path, required_count):
    if not output_path.exists():
        return {}
    data = load_json(output_path)
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        return {}
    return {
        row.get("record_id"): row
        for row in data["records"]
        if isinstance(row, dict)
        and isinstance(row.get("record_id"), str)
        and has_enough_candidates(row, required_count)
    }


def is_duplicate_question(question, previous_questions):
    normalized = re.sub(r"\s+", " ", (question or "").casefold()).strip()
    if not normalized:
        return False
    for previous in previous_questions:
        prev_norm = re.sub(r"\s+", " ", (previous or "").casefold()).strip()
        if normalized == prev_norm:
            return True
    return False


def generate_one_candidate(args, system_prompt, prompt_text, candidate_number, total_candidates, previous_questions):
    user_prompt = build_single_candidate_prompt(
        prompt_text,
        candidate_number,
        total_candidates,
        previous_questions,
    )

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
            parsed = parse_single_llm_output(raw_output)
            question = parsed.get("question") or ""
            if not question:
                last_error = "no_question_found"
            elif is_duplicate_question(question, previous_questions):
                last_error = "duplicate_question"
            else:
                return {
                    "raw_output": raw_output,
                    "explanation": parsed["explanation"],
                    "question": question,
                    "parse_status": parsed["parse_status"],
                    "error": None,
                    "attempts": attempt,
                }
        except Exception as exc:
            last_error = str(exc)

        if attempt < args.max_retries:
            time.sleep(args.retry_sleep)

    return {
        "raw_output": last_raw_output,
        "explanation": "",
        "question": "",
        "parse_status": "failed",
        "error": last_error or "unknown_error",
        "attempts": args.max_retries,
    }

def main():
    parser = argparse.ArgumentParser(
        description="OmniSQL-style step 4: call an LLM in a loop and generate question candidates."
    )
    parser.add_argument("--input", required=True, help="omnisql_step3 JSON file")
    parser.add_argument("--output", required=True, help="step-4 output JSON file")
    parser.add_argument("--model", required=True, help="Ollama model name")
    parser.add_argument("--url", default="http://localhost:11434/api/chat")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--num-predict", type=int, default=700)
    parser.add_argument("--num-candidates", type=int, default=5)
    parser.add_argument("--min-candidates", type=int, default=3, help="Minimum valid candidates required for a usable record")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--limit", type=int, help="Optional number of records for a dry run")
    parser.add_argument("--resume", action="store_true", help="Reuse already generated records in output")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    data = load_json(input_path)

    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("input must be a step-3 object with a records list")

    records = data["records"]
    if args.limit is not None:
        records = records[: args.limit]

    completed = existing_records_by_id(output_path, args.min_candidates) if args.resume else {}
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

        prompt = record.get("question_prompt") or {}
        system_prompt = prompt.get("system") or ""
        base_user_prompt = prompt.get("user") or ""

        out = dict(record)
        out["question_generation"] = {
            "method": "omnisql_style_sql_to_question_looped_candidates",
            "model": args.model,
            "status": "failed",
            "raw_output": "",
            "explanation": "",
            "candidates": [],
            "candidate_generations": [],
            "error": None,
            "num_candidates_requested": args.num_candidates,
            "min_candidates_required": args.min_candidates,
        }

        previous_questions = []
        explanations = []
        candidate_errors = []

        for candidate_number in range(1, args.num_candidates + 1):
            generated_candidate = generate_one_candidate(
                args,
                system_prompt,
                base_user_prompt,
                candidate_number,
                args.num_candidates,
                previous_questions,
            )
            out["question_generation"]["candidate_generations"].append(
                {
                    "candidate_number": candidate_number,
                    **generated_candidate,
                }
            )

            question = generated_candidate.get("question") or ""
            if question:
                candidate_id = chr(ord("A") + len(previous_questions))
                out["question_generation"]["candidates"].append(
                    {
                        "candidate_id": candidate_id,
                        "question": question,
                    }
                )
                previous_questions.append(question)

            explanation = generated_candidate.get("explanation") or ""
            if explanation:
                explanations.append(explanation)

            if generated_candidate.get("error"):
                candidate_errors.append(
                    f"candidate {candidate_number}: {generated_candidate.get('error')}"
                )

        candidates = out["question_generation"]["candidates"]
        out["question_generation"]["explanation"] = explanations[0] if explanations else ""
        out["question_generation"]["raw_output"] = "\n\n---CANDIDATE-CALL---\n\n".join(
            item.get("raw_output") or ""
            for item in out["question_generation"]["candidate_generations"]
        )
        out["question_generation"]["status"] = "ok" if len(candidates) >= args.min_candidates else "failed"
        out["question_generation"]["error"] = "; ".join(candidate_errors) if candidate_errors else None

        if len(candidates) >= args.min_candidates:
            generated += 1
        else:
            failed += 1
            missing_count = args.num_candidates - len(candidates)
            if missing_count > 0:
                candidate_errors.append(f"missing {missing_count} candidate(s)")
                out["question_generation"]["error"] = "; ".join(candidate_errors)

        out["pipeline_state"] = dict(record.get("pipeline_state") or {})
        out["pipeline_state"]["step"] = "omnisql_step4_question_candidates_looped"
        output_records.append(out)

        if index % 25 == 0 or index == len(records):
            result = {
                "dataset_type": "omnisql_step4_question_candidates_looped",
                "source_file": str(input_path),
                "model": args.model,
                "input_records": len(records),
                "output_records": len(output_records),
                "generated_records": generated,
                "reused_records": reused,
                "failed_records": failed,
                "num_candidates": args.num_candidates,
                "min_candidates": args.min_candidates,
                "records": output_records,
            }
            write_json(output_path, result)
            print(
                f"[{index}/{len(records)}] generated={generated} reused={reused} failed={failed}"
            )

    result = {
        "dataset_type": "omnisql_step4_question_candidates_looped",
        "source_file": str(input_path),
        "model": args.model,
        "input_records": len(records),
        "output_records": len(output_records),
        "generated_records": generated,
        "reused_records": reused,
        "failed_records": failed,
        "num_candidates": args.num_candidates,
                "min_candidates": args.min_candidates,
        "records": output_records,
    }
    write_json(output_path, result)

    print(f"Input records: {len(records)}")
    print(f"Output records: {len(output_records)}")
    print(f"Generated records: {generated}")
    print(f"Reused records: {reused}")
    print(f"Failed records: {failed}")
    print(f"Candidates requested per record: {args.num_candidates}")
    print(f"Minimum candidates required: {args.min_candidates}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()





