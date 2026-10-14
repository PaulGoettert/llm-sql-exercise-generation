import argparse
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "master_records2_with_repair_prompt.json"
DEFAULT_OUTPUT = ROOT / "single_sql_dataset.jsonl"


def get_system(entry):
    repair_system = entry.get("repair_system_prompt") if isinstance(entry, dict) else None
    if isinstance(repair_system, str):
        return repair_system
    return ""


def get_user_prompt(entry):
    task_prompt = entry.get("task_prompt", {}) if isinstance(entry, dict) else {}
    messages = task_prompt.get("messages") if isinstance(task_prompt, dict) else None
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                return msg.get("content", "") or ""
    return ""


def normalize_sql(sql_text):
    if not isinstance(sql_text, str):
        sql_text = ""
    stripped = sql_text.strip()
    if stripped.startswith("<SQL>") and stripped.endswith("</SQL>"):
        stripped = stripped[len("<SQL>") : -len("</SQL>")].strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].strip()
    return stripped.strip()


def normalize_and_wrap(sql_text):
    return f"<SQL>{normalize_sql(sql_text)}</SQL>"


def derive_record_id(entry):
    rid = entry.get("record_id")
    if isinstance(rid, str) and rid.strip():
        return rid.strip()

    expected_diff = entry.get("expected_diff")
    entry_index = entry.get("entry_index")
    if isinstance(expected_diff, int) and isinstance(entry_index, int):
        return f"diff{expected_diff}_entry{entry_index:04d}"

    meta = entry.get("meta")
    if isinstance(meta, dict):
        prompt_id = meta.get("prompt_id")
        idx = meta.get("entry_index")
        if isinstance(prompt_id, str) and isinstance(idx, int):
            return f"{prompt_id}_entry{idx:04d}"

    return None


def pick_original_query(entry):
    for key in ("original_query", "generated_query", "candidate_sql", "query_text", "query"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def build_record(entry):
    out = dict(entry)

    record_id = derive_record_id(entry)
    if record_id:
        out["record_id"] = record_id

    # Keep the original query immutable for later comparison/merging.
    if not (isinstance(out.get("original_query"), str) and out.get("original_query").strip()):
        out["original_query"] = pick_original_query(entry)

    system = get_system(entry)
    prompt = entry.get("repair_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        prompt = get_user_prompt(entry)

    # Provide model2 expected fields explicitly while preserving full payload.
    out["model1_system"] = system
    out["model1_prompt"] = prompt or ""

    candidate = entry.get("candidate_sql")
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = out.get("original_query") or ""

    out["model1_sql_query"] = normalize_and_wrap(candidate)

    if "model1_test_score" not in out and isinstance(entry.get("test_score"), dict):
        out["model1_test_score"] = entry.get("test_score")

    # Convenience aliases used by some runs/tools.
    out["system"] = out["model1_system"]
    out["prompt"] = out["model1_prompt"]
    out["sql_query"] = out["model1_sql_query"]

    # Keep structural fields available for model2 postprocessing/quoting.
    # Prefer canonical names; fall back to prefixed aliases if present.
    for key in ("db_id", "column_types", "primary_keys", "sample_rows", "foreign_keys"):
        if out.get(key) is None and entry.get(f"model1_{key}") is not None:
            out[key] = entry.get(f"model1_{key}")

    return out


def main():
    parser = argparse.ArgumentParser(
        description="Build a single-query dataset (record_id/system/prompt/sql_query) from canonical JSON records."
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input JSON file path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL file path")
    args = parser.parse_args()

    in_path = pathlib.Path(args.input)
    out_path = pathlib.Path(args.output)

    data = json.loads(in_path.read_text(encoding="utf-8"))
    written = 0

    with out_path.open("w", encoding="utf-8") as f:
        for entry in data:
            row = build_record(entry)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

    print(f"Wrote {written} rows to {out_path}")


if __name__ == "__main__":
    main()
