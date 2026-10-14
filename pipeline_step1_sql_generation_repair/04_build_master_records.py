import json
import pathlib
import re

ROOT = pathlib.Path(".")
RES_DIR = ROOT / "resources"
ANA_DIR = ROOT / "analyse feedback"
OUT2_DIR = ROOT / "output2"
OUT_PATH = ROOT / "master_records.json"

def extract_prompt_id(res_name):
    m = re.search(r"(diff\d+_prompt\d+_limit\d+)", res_name)
    return m.group(1) if m else None


def clean_parse_validate_error(err):
    if not isinstance(err, str) or not err:
        return None
    if ":" in err:
        return err.rsplit(":", 1)[-1]
    return err

def main():
    res_files = sorted(RES_DIR.glob("*.json"))
    out = []

    for res_path in res_files:
        prompt_id = extract_prompt_id(res_path.name)
        if not prompt_id:
            continue

        ana_name = f"step2_output_{prompt_id}_after_lint.json"
        ana_path = ANA_DIR / ana_name
        if not ana_path.exists():
            continue
        out2_path = OUT2_DIR / ana_name
        if not out2_path.exists():
            continue

        res_data = json.loads(res_path.read_text(encoding="utf-8"))
        ana_data = json.loads(ana_path.read_text(encoding="utf-8"))
        out2_data = json.loads(out2_path.read_text(encoding="utf-8"))

        analysis = ana_data.get("analysis", [])
        for idx, res_entry in enumerate(res_data):
            if idx >= len(analysis):
                break
            ana_entry = analysis[idx]
            out2_entry = out2_data[idx] if idx < len(out2_data) else {}
            parse_validate_error = clean_parse_validate_error(
                out2_entry.get("parse_validate_error") if isinstance(out2_entry, dict) else None
            )

            master = {
                "db_id": f"{res_entry.get('db_id','')}_{res_path.stem}",
                "task_prompt": res_entry.get("prompt"),
                "candidate_sql": ana_entry.get("query_text"),
                "tests": ana_entry.get("tests"),
                "meta": {
                    "source_file": res_path.name,
                    "analysis_file": ana_path.name,
                    "entry_index": idx,
                    "prompt_id": prompt_id,
                    "run_id": prompt_id,
                },
            }
            if parse_validate_error:
                master["parse_validate_error"] = parse_validate_error
            out.append(master)

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"Wrote {len(out)} records to {OUT_PATH}")

if __name__ == "__main__":
    main()
