import json
import logging
import os
import re
import time

import requests
from sqlglot import parse_one
from sqlglot.expressions import Alias, Column, Identifier, Table


# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Runtime config
URL = "http://localhost:11434/api/chat"
MODEL_NAME = "Qwen3-with-adap"
INPUT_DATASET = os.path.join(os.path.dirname(__file__), "single_sql_dataset.jsonl")
MAX_MODEL_ATTEMPTS = 3
MAX_SQL_ATTEMPTS = 3

SQL_TAG_PATTERN = re.compile(r"<sql>(.*?)</sql>", re.IGNORECASE | re.DOTALL)
SQL_CODE_FENCE_PATTERN = re.compile(r"```(?:sql)?\s*([\s\S]+?)```", re.IGNORECASE)
SQL_EXTRACTION_PATTERN = re.compile(
    r"((SELECT|INSERT|UPDATE|DELETE|WITH)\s[\s\S]+?(?:;|$))",
    re.IGNORECASE,
)

SQL_KEYWORDS = {
    "select", "from", "where", "join", "left", "right", "inner", "outer", "full", "cross",
    "on", "group", "by", "order", "having", "limit", "offset", "union", "all", "distinct",
    "as", "case", "when", "then", "else", "end", "and", "or", "not", "in", "is", "null",
    "like", "between", "exists", "with", "insert", "into", "update", "delete", "values",
    "create", "drop", "alter", "table", "view", "database", "primary", "foreign", "key"
}

def get_first(row, *keys):
    for key in keys:
        val = row.get(key)
        if val is not None:
            return val
    return None


def extract_sql(text):
    if not isinstance(text, str):
        return ""

    tag_match = SQL_TAG_PATTERN.findall(text)
    if tag_match:
        sql = tag_match[-1].strip()
        if sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    code_blocks = SQL_CODE_FENCE_PATTERN.findall(text)
    for block in reversed(code_blocks):
        block = block.strip()
        if not block:
            continue
        block_match = SQL_EXTRACTION_PATTERN.findall(block)
        if block_match:
            sql = block_match[-1][0].strip()
            if sql.endswith(";"):
                sql = sql[:-1].strip()
            return sql

    matches = SQL_EXTRACTION_PATTERN.findall(text)
    if matches:
        sql = matches[-1][0].strip()
        if sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    lower_text = text.lower()
    if "<sql" in lower_text:
        idx = lower_text.rfind("<sql")
        start = text.find(">", idx)
        if start != -1:
            fragment = text[start + 1 :]
            end_idx = fragment.lower().find("</sql>")
            if end_idx != -1:
                fragment = fragment[:end_idx]
            fragment = fragment.strip()
            if fragment.endswith(";"):
                fragment = fragment[:-1].strip()
            if fragment:
                return fragment

    stripped = text.strip()
    if stripped.startswith("<SQL>") and stripped.endswith("</SQL>"):
        stripped = stripped[len("<SQL>") : -len("</SQL>")].strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].strip()
    if stripped:
        return stripped

    fallback_lines = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue
        if stripped_line.upper().startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "WITH")):
            fallback_lines.append(stripped_line)
    if fallback_lines:
        return fallback_lines[-1]

    return ""


def is_plausible_sql(sql):
    if not isinstance(sql, str):
        return False
    stripped = sql.strip()
    if not stripped:
        return False
    if not stripped.upper().startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "WITH")):
        return False
    try:
        parse_one(stripped, read="mysql")
    except Exception:
        return False
    return True


def collect_identifier_sets(row):
    column_types = get_first(row, "column_types", "model1_column_types")
    if not isinstance(column_types, dict):
        return set(), set()
    table_names = {str(tbl).lower() for tbl in column_types.keys()}
    column_names = set()
    for cols in column_types.values():
        if isinstance(cols, dict):
            for col in cols.keys():
                column_names.add(str(col).lower())
    return column_names, table_names


def escape_reserved_words(query, column_names, table_names):
    if not isinstance(query, str):
        return query, "query_not_string"

    query = re.sub(
        r'\bAS\s+["`]+(.+?)["`]+',
        lambda m: "AS `{}`".format(m.group(1).strip('`"')),
        query,
        flags=re.IGNORECASE | re.DOTALL,
    )

    try:
        tree = parse_one(query, read="postgres")

        def visit(node):
            if isinstance(node, Table):
                db = node.args.get("db")
                if isinstance(db, Identifier):
                    node.set("db", Identifier(this=db.this, quoted=True))
                elif isinstance(db, str):
                    node.set("db", Identifier(this=db, quoted=True))
                if node.name and node.name.lower() in table_names:
                    node.set("this", Identifier(this=node.name, quoted=True))

            if isinstance(node, Column):
                qual = node.args.get("table")
                if isinstance(qual, Identifier) and qual.this and qual.this.lower() in table_names:
                    node.set("table", Identifier(this=qual.this, quoted=True))
                col = node.args.get("this")
                if isinstance(col, Identifier) and col.this and col.this.lower() in column_names:
                    node.set("this", Identifier(this=col.this, quoted=True))

            if isinstance(node, Alias):
                alias_id = node.args.get("alias")
                if alias_id and hasattr(alias_id, "this") and isinstance(alias_id.this, str):
                    clean = alias_id.this.strip('`"')
                    node.set("alias", Identifier(this=clean, quoted=True))

            for arg in node.args.values():
                if isinstance(arg, list):
                    for child in arg:
                        if hasattr(child, "args"):
                            visit(child)
                elif hasattr(arg, "args"):
                    visit(arg)

        visit(tree)
        return tree.sql(dialect="mysql"), None
    except Exception as exc:
        return query, str(exc)


def regex_quote_identifiers(query, column_names, table_names):
    if not isinstance(query, str):
        return query

    # Quote longer identifiers first to avoid partial overlaps.
    all_names = sorted(set(column_names) | set(table_names), key=len, reverse=True)
    if not all_names:
        return query

    # Apply replacements only outside of single-quoted string literals.
    # This avoids corrupting values like 'Mexico City'.
    parts = re.split(r"('(?:''|[^'])*')", query)

    for i, part in enumerate(parts):
        # odd indices are quoted string literals
        if i % 2 == 1:
            continue

        out = part
        for name in all_names:
            if not name:
                continue

            # Never quote SQL keywords as identifiers (e.g. FROM, END)
            if name.lower() in SQL_KEYWORDS:
                continue

            # Skip if already quoted by backticks or double quotes.
            pattern = re.compile(rf'(?<![`"])\b({re.escape(name)})\b(?![`"])', flags=re.IGNORECASE)
            out = pattern.sub(lambda m: f"`{m.group(1)}`", out)

        parts[i] = out

    return "".join(parts)

def finalize_sql(raw_sql, row, strict):
    sql = extract_sql(raw_sql or "")
    if not sql:
        return None, "empty_sql"

    column_names, table_names = collect_identifier_sets(row)

    # Preserve existing quoting from model1 inputs; AST re-serialization can drop quotes.
    if "`" in sql:
        escaped_sql = sql
        escape_err = None
    else:
        escaped_sql, escape_err = escape_reserved_words(sql, column_names, table_names)

    # Fallback quoting pass to mirror model1 robustness on reserved identifiers.
    escaped_sql = regex_quote_identifiers(escaped_sql, column_names, table_names)

    if strict and not is_plausible_sql(escaped_sql):
        return None, "not_plausible_after_escape"

    return escaped_sql, escape_err


def load_all_rows(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows.append(obj)
    return rows


def call_ollama(system_prompt, user_prompt):
    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt or ""},
            {"role": "user", "content": user_prompt or ""},
        ],
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 3000,
            "stop": ["</SQL>"],
        },
    }

    for attempt in range(1, MAX_MODEL_ATTEMPTS + 1):
        try:
            resp = requests.post(URL, json=payload, timeout=120)
        except Exception as e:
            logging.error("[Ollama] HTTP error attempt %s/%s: %s", attempt, MAX_MODEL_ATTEMPTS, e)
            time.sleep(1.0)
            continue

        if resp.status_code != 200:
            logging.error("[Ollama] HTTP %s attempt %s/%s: %s", resp.status_code, attempt, MAX_MODEL_ATTEMPTS, resp.text[:500])
            time.sleep(1.0)
            continue

        try:
            resp_json = resp.json()
        except Exception as e:
            logging.error("[Ollama] JSON parse error attempt %s/%s: %s", attempt, MAX_MODEL_ATTEMPTS, e)
            logging.error("Raw body: %s", resp.text[:500])
            time.sleep(1.0)
            continue

        msg_obj = resp_json.get("message") or {}
        content = (msg_obj.get("content") or resp_json.get("response") or "").strip()
        if content:
            return content, None

        logging.warning("[Ollama] empty content attempt %s/%s", attempt, MAX_MODEL_ATTEMPTS)
        time.sleep(1.0)

    return "", "no_content_after_retries"


def numeric_score(record):
    score_obj = get_first(record, "model1_test_score", "test_score")
    val = score_obj.get("score") if isinstance(score_obj, dict) else None
    try:
        return float(val)
    except Exception:
        return None


def pick_existing_sql(record):
    return get_first(
        record,
        "model1_sql_query",
        "sql_query",
        "original_query",
        "candidate_sql",
        "query_text",
        "query",
    )


def main():
    rows = load_all_rows(INPUT_DATASET)
    logging.info("Loaded %s rows from %s", len(rows), INPUT_DATASET)

    missing_column_types = sum(
        1 for row in rows if not isinstance(get_first(row, "column_types", "model1_column_types"), dict)
    )
    if missing_column_types:
        raise ValueError(
            f"Input dataset is missing column_types in {missing_column_types}/{len(rows)} rows. "
            "Model2 quoting requires schema fields; rebuild single_sql_dataset.jsonl with structural fields."
        )

    output_rows = []
    generated_count = 0
    copied_perfect_count = 0
    skipped_other_count = 0

    for row in rows:
        out = dict(row)

        if out.get("record_id") is None and out.get("model1_record_id") is not None:
            out["record_id"] = out.get("model1_record_id")

        if not (isinstance(out.get("original_query"), str) and out.get("original_query").strip()):
            out["original_query"] = extract_sql(
                get_first(out, "model1_sql_query", "sql_query", "candidate_sql", "query_text") or ""
            )

        score = numeric_score(row)

        if score == 37:
            primary_sql = pick_existing_sql(row)
            final_sql, escape_err = finalize_sql(primary_sql, row, strict=True)
            if final_sql is None:
                fallback_candidates = [
                    out.get("original_query"),
                    get_first(row, "original_query", "sql_query", "model1_sql_query"),
                    get_first(row, "candidate_sql", "query_text", "query"),
                ]
                for cand in fallback_candidates:
                    cand_sql, cand_err = finalize_sql(cand, row, strict=False)
                    if cand_sql:
                        final_sql = cand_sql
                        if not escape_err and cand_err:
                            escape_err = cand_err
                        out["postprocess_fallback_used"] = True
                        break
            out["generated_query"] = final_sql
            if final_sql is None:
                out["generation_error"] = "no_valid_sql_after_postprocess"
                out["model2_action"] = "generated_failed"
            else:
                out["model2_action"] = "copied_perfect_score"
            if escape_err:
                out["escape_reserved_words_error"] = escape_err
            output_rows.append(out)
            copied_perfect_count += 1
            continue

        if score is not None and score < 37:
            system_prompt = get_first(row, "model1_system", "system") or ""
            user_prompt = get_first(row, "model1_prompt", "prompt") or ""

            best_sql = None
            best_raw_output = None
            best_escape_err = None
            last_error = None

            for sql_attempt in range(1, MAX_SQL_ATTEMPTS + 1):
                model_text, err = call_ollama(system_prompt, user_prompt)
                if err:
                    last_error = err
                    continue

                best_raw_output = model_text
                sql, escape_err = finalize_sql(model_text, row, strict=True)
                if sql is None:
                    last_error = "no_valid_sql_after_postprocess"
                    continue

                best_sql = sql
                best_escape_err = escape_err
                break

            out["model_raw_output"] = best_raw_output
            out["generated_query"] = best_sql
            if best_sql is None:
                out["generation_error"] = last_error or "no_valid_sql_after_retries"
                out["model2_action"] = "generated_failed"
            else:
                out["model2_action"] = "generated_from_model2"
                if best_escape_err:
                    out["escape_reserved_words_error"] = best_escape_err
            output_rows.append(out)
            generated_count += 1
            continue

        final_sql, escape_err = finalize_sql(get_first(row, "model1_sql_query", "sql_query"), row, strict=True)
        out["generated_query"] = final_sql
        if final_sql is None:
            out["generation_error"] = "no_valid_sql_after_postprocess"
            out["model2_action"] = "generated_failed"
            output_rows.append(out)
            skipped_other_count += 1
            continue
        if escape_err:
            out["escape_reserved_words_error"] = escape_err
        out["model2_action"] = "copied_unhandled_score"
        output_rows.append(out)
        skipped_other_count += 1

    filename = "model2_output_all_limit140.json"
    output_path = os.path.join(os.path.dirname(__file__), filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_rows, f, indent=2, ensure_ascii=False)

    print(f"Saved: {output_path}")
    print(
        "Stats: "
        f"generated={generated_count}, "
        f"copied_score37={copied_perfect_count}, "
        f"copied_other={skipped_other_count}"
    )


if __name__ == "__main__":
    main()



