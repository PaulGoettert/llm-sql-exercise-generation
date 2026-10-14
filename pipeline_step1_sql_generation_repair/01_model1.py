from determine_difficulty import determine_difficulty
import os
import base64
import json
import logging
import requests
import time
import re
import sys
import random
import importlib.util
from pathlib import Path
import sqlglot
from sqlglot import parse_one
from sqlglot.expressions import Table, Column, Identifier, Alias

SCRIPT_DIR = Path(__file__).resolve().parent


def load_local_module(filename, module_name):
    module_path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


table_description_mod = load_local_module("02_table_description.py", "table_description_mod")
random_sql_query_mod = load_local_module("03_random_sql_query.py", "random_sql_query_mod")
generate_schema_description = table_description_mod.generate_schema_description
get_handcrafted_examples = random_sql_query_mod.get_handcrafted_examples


MAX_ATTEMPTS_PER_QUERY = 3  # wie oft soll pro Query neu versucht werden?


def call_ollama(payload, max_retries=MAX_ATTEMPTS_PER_QUERY):
    payload = dict(payload)
    payload["stream"] = False
    #payload["think"] = "low"

    last_resp_json = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=120)
        except Exception as e:
            logging.error(f"[Ollama] HTTP error (attempt {attempt}/{max_retries}): {e}")
            time.sleep(1.0)
            continue

        if resp.status_code != 200:
            logging.error(
                f"[Ollama] HTTP {resp.status_code} (attempt {attempt}/{max_retries}): "
                f"{resp.text[:500]}"
            )
            time.sleep(1.0)
            continue

        try:
            resp_json = resp.json()
            last_resp_json = resp_json
        except Exception as e:
            logging.error(f"[Ollama] JSON parse error (attempt {attempt}/{max_retries}): {e}")
            logging.error(f"Raw body: {resp.text[:500]}")
            time.sleep(1.0)
            continue

        msg_obj = resp_json.get("message") or {}
        output_message = (
            msg_obj.get("content", "")
            or resp_json.get("response", "")  # Fallback für generate-Style
            or ""
        )

        logging.info(
            f"[Ollama] attempt {attempt}/{max_retries}, raw model output: "
            f"{repr(output_message)[:300]}"
        )

        if output_message.strip():
            return output_message

        logging.warning(
            f"[Ollama] empty content (attempt {attempt}/{max_retries}). "
            f"Short JSON: {json.dumps(resp_json)[:300]}"
        )
        time.sleep(1.0)

    logging.error(
        f"[Ollama] all {max_retries} attempts returned empty content. "
        f"Last JSON: {json.dumps(last_resp_json)[:500] if last_resp_json else 'None'}"
    )
    return ""


def is_plausible_sql(sql: str) -> bool:
    """
    Sehr simple Plausibilitätsprüfung:
    - nicht leer
    - beginnt mit einem SQL-Keyword
    - optional: parse_one() darf nicht hart fehlschlagen
    """
    if not sql:
        return False

    stripped = sql.strip()
    if not stripped:
        return False

    upper = stripped.upper()
    if not upper.startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "WITH")):
        return False

    # Optional: syntaktische Prüfung mit sqlglot, wenn das mal zickt, kannst du den try/except auskommentieren
    try:
        parse_one(stripped, read="mysql")
    except Exception as e:
        logging.warning(f"is_plausible_sql: sqlglot parse failed: {e} | SQL={stripped!r}")
        return False

    return True



# Funktion zum Escapen basierend auf Parser-Output
# Identifier (Spalten-/Tabellenamen) werden gequoted, echte SQL-Keywords bleiben unberührt.
def escape_reserved_words(query: str,
                          column_names: set,
                          table_names: set) -> (str, str):
    """
    1) Alias-Cleanup vor dem Parse: entfernt beliebige ` und " um den Aliastext
       und schreibt ihn dann als AS `aliastext`.
    2) Parst mit sqlglot (Postgres-Dialekt) und markiert alle Table/Column/Alias-Nodes
       als quoted Identifiers.
    3) Serialisiert mit dem MySQL-Dialekt, damit alle quoted Identifiers
       sauber mit Backticks ausgegeben werden.
    4) Fällt der Parse aus, gibt es einen Regex-Fallback, der
       alle table_names und column_names in Backticks setzt
       und einfache Aliase ebenfalls quotet.
    """
    # 0) Alias-Normalisierung (jetzt ohne f-String und Backslashes)
    query = re.sub(
        r'\bAS\s+["`]+(.+?)["`]+',
        lambda m: "AS `{}`".format(m.group(1).strip('`"')),
        query,
        flags=re.IGNORECASE | re.DOTALL
    )

    try:
        # 1) Parse im Postgres-Dialekt
        tree = parse_one(query, read="postgres")

        # 2) AST-Visitor: alle relevanten Knoten als quoted Identifiers markieren
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
                if isinstance(qual, Identifier) and qual.this.lower() in table_names:
                    node.set("table", Identifier(this=qual.this, quoted=True))
                col = node.args.get("this")
                if isinstance(col, Identifier) and col.this.lower() in column_names:
                    node.set("this", Identifier(this=col.this, quoted=True))

            if isinstance(node, Alias):
                alias_id = node.args.get("alias")
                if alias_id and hasattr(alias_id, "this"):
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
        # 3) Serialisieren im MySQL-Dialekt (Backticks um alles, was quoted=True ist)
        return tree.sql(dialect="mysql"), None

    except Exception as e:
        # Im Fehlerfall: unveränderten Query zurückgeben + Error-Text
        return query, str(e)


#set dataset limit
#trai ndataset has 140 unique databases
limit = 140

queries_per_db = 5  # Anzahl der gewünschten SQL-Queries pro Datenbank


# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def load_dataset_from_file(path, limit=None):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    unique = []
    seen = set()

    for item in data:
        db_id = item["db_id"]
        if db_id in seen:
            continue
        seen.add(db_id)
        unique.append(item)
        if limit is not None and len(unique) >= limit:
            break

    return unique


# Difficulty Mapping
difficulty_mapping = {
    "1": "simple SQL statements with a single table, without JOIN and without aggregation, only with WHERE",
    "2": "SQL statements with JOIN without aggregation (monotone queries)",
    "3": "SQL statements with NOT EXISTS or NOT IN without aggregation (non-monotone queries)",
    "4": "SQL statements with aggregation functions without GROUP BY",
    "5": "SQL statements with aggregation functions with GROUP BY",
    "6": "SQL statements with aggregation functions with GROUP BY and HAVING",
    "7": "SQL statements with UNION and LEFT JOIN",
    "8": "SQL statements with LEFT JOIN and aggregation with GROUP BY, count including zero results"
}

# Prompt Selection Mapping
prompt_mapping = {
    "1": "standard",
    "2": "divide_and_conquer",
    "3": "query_plan",
    "4": "few_shot"
}

# Parameter abfragen (Anzahl + Gültigkeit)
if len(sys.argv) < 3:
    print("❌ Fehler: Du musst mindestens 2 Parameter übergeben.")
    print("📌 Aufruf: python3 test.py <difficulty_level> <prompt_type>")
    print("Beispiel: python3 test.py 1 1")
    sys.exit(1)

difficulty_level = sys.argv[1]
prompt_type_code = sys.argv[2]

if difficulty_level not in difficulty_mapping or prompt_type_code not in prompt_mapping:
    print("❌ Fehler: Ungültiger Parameterwert.")
    print("📌 Aufruf: python3 test.py <difficulty_level> <prompt_type>")
    print("\nValid difficulty levels:")
    for key, value in difficulty_mapping.items():
        print(f"{key}: {value}")
    print("\nValid prompt types:")
    for key, value in prompt_mapping.items():
        print(f"{key}: {value}")
    sys.exit(1)


sql_difficulty = difficulty_mapping[difficulty_level]
prompt_type = prompt_mapping[prompt_type_code]
print(f"Selected difficulty level {difficulty_level}: {sql_difficulty}")
print(f"Selected prompt type {prompt_type_code}: {prompt_type}")

# Modell-URL
url = "http://localhost:11434/api/chat"

# Liste mit Datensätzen
dataset_path = os.path.join(os.path.dirname(__file__), "final_dataset.json")
dataset_list = load_dataset_from_file(dataset_path, limit)  # <== hier kannst du limit ändern oder None setzen
logging.info(f"Loaded {len(dataset_list)} unique databases from dataset.")
logging.info(f"First db_id: {dataset_list[0]['db_id'] if dataset_list else 'NONE'}")


# Modell-Name
model_name = "Arctic-Text2SQL-R1-7B.f16"

# Liste und Aufzählung verwandeln
def format_list(items):
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else (items[0] if items else "")

SQL_TAG_PATTERN = re.compile(r"<sql>(.*?)</sql>", re.IGNORECASE | re.DOTALL)
SQL_CODE_FENCE_PATTERN = re.compile(r"```(?:sql)?\s*([\s\S]+?)```", re.IGNORECASE)
SQL_EXTRACTION_PATTERN = re.compile(
    r"((SELECT|INSERT|UPDATE|DELETE|WITH)\s[\s\S]+?(?:;|$))",
    re.IGNORECASE
)


def extract_sql(text):
    tag_match = SQL_TAG_PATTERN.findall(text)
    if tag_match:
        sql = tag_match[-1].strip()
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
            if sql:
                return sql

    matches = SQL_EXTRACTION_PATTERN.findall(text)
    if matches:
        sql = matches[-1][0].strip()
        if sql.endswith(";"):
            sql = sql[:-1].strip()
        return sql

    fallback_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "WITH")):
            fallback_lines.append(stripped)
    if fallback_lines:
        return fallback_lines[-1]

    return ""

def format_primary_key_mapping(pk_dict: dict) -> str:
    lines = []
    for table, keys in pk_dict.items():
        if not keys:
            lines.append(f"- {table}: none")
        elif len(keys) == 1:
            lines.append(f"- {table}: {keys[0]}")
        else:
            key_list = ", ".join(keys)
            lines.append(f"- {table}: {key_list}")
    if not lines:
        return "Primary keys: none"
    return "Primary keys:\n" + "\n".join(lines)


def format_foreign_key_details(foreign_keys):
    if not foreign_keys:
        return "Foreign keys: none"

    lines = []
    for fk in foreign_keys:
        lines.append(f"- {fk.strip()}")
    return "Foreign keys:\n" + "\n".join(lines)

# Standard Prompt
def generate_standard_prompt(data, sql_difficulty):
    pk_mapping_str = format_primary_key_mapping(data["primary_keys"])
    foreign_keys = format_foreign_key_details(data['foreign_keys'])
    return {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a database expert. You receive database schema information and a difficulty level. "
                    "Your task is to generate a single SQL query that matches the requested difficulty and can serve "
                    "as a basis for creating exam questions. The query must be correct, clear and didactic. "
                    "You may think step by step internally before answering, but you must never write your reasoning, "
                    "analysis, comments or explanations in the output. "
                    "Do not ask the user any questions. If something is unspecified, choose reasonable values yourself. "
                    "Your entire output must be exactly one valid SQL query formatted as <SQL>SELECT ...</SQL>. "
                    "Do not include anything else: no natural language text, no comments, no markdown code fences, "
                    "and no second <SQL>...</SQL> block."
                )
            },
            {
                "role": "user",
                "content": (
                    f"You are looking at the database {data['db_id']}.\n"
                    f"Schema: {generate_schema_description(data['column_types'], data['sample_rows'], data['foreign_keys'])}\n"
                    f"{pk_mapping_str}\n"
                    f"{foreign_keys}\n"
                    f"The SQL query you should generate has to be a {sql_difficulty}. "
                    f"Return only the SQL query wrapped in <SQL> and </SQL> with no additional text."
                )
            }
        ],
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 3000,
            "stop": ["</SQL>"]
        }
    }

# Divide and Conquer Prompt
def generate_divide_and_conquer_prompt(data, sql_difficulty):
    db_id = data['db_id']
    schema_desc = generate_schema_description(data["column_types"], data["sample_rows"], data["foreign_keys"])
    pk_mapping_str = format_primary_key_mapping(data["primary_keys"])
    foreign_keys = format_foreign_key_details(data['foreign_keys'])

    return {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a database expert using an internal three-step divide-and-conquer strategy. "
                    "Use the steps only as internal reasoning: do not describe them or your thought process in the output. "
                    "Step 1 (internal): analyse the schema and relationships. "
                    "Step 2 (internal): plan the joins, filters, aggregations and structure that match the requested difficulty. "
                    "Step 3 (output): write the final SQL query. "
                    "You may think step by step internally, but the final answer must not contain any reasoning, analysis, or comments. "
                    "You will receive database schema information and a difficulty level. Generate an SQL query that matches the difficulty level "
                    "and can serve as a basis for creating exam questions. The query should be clear, didactic and suitable for question generation. "
                    "Do not ask the user any questions. If something is unspecified, choose reasonable values yourself. "
                    "Your entire output must be exactly one valid SQL query formatted as <SQL>SELECT ...</SQL>. "
                    "Do not include anything else: no natural language text, no comments, no markdown code fences, "
                    "and no second <SQL>...</SQL> block."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Step 1 (internal): analyse the database {db_id} using the information below and identify the key tables, attributes, "
                    f"relationships, and any useful example values. Do not output this analysis.\n"
                    f"Schema: {schema_desc}\n"
                    f"{pk_mapping_str}\n"
                    f"{foreign_keys}"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Step 2 (internal): based on Step 1, decide which joins, filters, aggregations or other constructs are needed for a query "
                    f"with difficulty '{sql_difficulty}'. Check internally that the planned operations match this difficulty. "
                    "Do not output this reasoning."
                )
            },
            {
                "role": "user",
                "content": (
                    "Step 3 (output): now produce the final SQL query that implements the Step 2 plan. "
                    "Return only the SQL query wrapped in <SQL> and </SQL> (no labels, no commentary, no explanation)."
                )
            }
        ],
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 3000,
            "stop": ["</SQL>"]
        }
    }


# Query Plan CoT Prompt
def generate_query_plan_prompt(data, sql_difficulty):
    db_id = data['db_id']
    schema_desc = generate_schema_description(data["column_types"], data["sample_rows"], data["foreign_keys"])
    pk_mapping_str = format_primary_key_mapping(data["primary_keys"])
    foreign_keys = format_foreign_key_details(data['foreign_keys'])

    return {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a database expert. You may reason step by step internally before answering, "
                    "but you must never write your reasoning, intermediate steps, or comments in the output. "
                    "Use an internal plan (identify tables, join paths, filters, aggregations, etc.) and then output only the final query. "
                    "You will receive database schema information and a difficulty level. Generate an SQL query that matches the difficulty level "
                    "and can serve as a basis for creating exam questions later. The query should be clear, didactic and suitable for question generation. "
                    "Do not ask the user any questions. If something is unspecified, choose reasonable values yourself. "
                    "Your entire output must be exactly one valid SQL query formatted as <SQL>SELECT ...</SQL>. "
                    "Do not include anything else: no natural language text, no comments, no markdown code fences, "
                    "and no second <SQL>...</SQL> block."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Context for database {db_id}:\n"
                    f"Schema: {schema_desc}\n"
                    f"{pk_mapping_str}\n"
                    f"{foreign_keys}\n"
                    f"Target difficulty: {sql_difficulty}"
                )
            },
            {
                "role": "user",
                "content": (
                    "Internally (do not show this), identify the relevant tables, join paths and key attributes based on the schema above. "
                    "Use the schema and sample values only for your internal planning."
                )
            },
            {
                "role": "user",
                "content": (
                    "Internally (do not show this), determine the filters, aggregations, grouping, HAVING clauses or set operations required "
                    "by the requested difficulty. Revise your internal plan if needed."
                )
            },
            {
                "role": "user",
                "content": (
                    "Internally (do not show this), outline the final SELECT/FROM/WHERE and, if needed, GROUP BY/HAVING structure."
                )
            },
            {
                "role": "user",
                "content": (
                    "Now output only the final SQL query text, wrapped in <SQL> and </SQL>, with no explanation, no labels and no comments."
                )
            }
        ],
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 3000,
            "stop": ["</SQL>"]
        }
    }


# Few-shot Synthetic Example Prompt
def generate_few_shot_prompt(data, sql_difficulty):
    db_id = data['db_id']
    schema_desc = generate_schema_description(data["column_types"], data["sample_rows"], data["foreign_keys"])
    pk_mapping_str = format_primary_key_mapping(data["primary_keys"])
    foreign_keys = format_foreign_key_details(data['foreign_keys'])

    example_queries = get_handcrafted_examples(difficulty_level, k=3)
    example_block = "\n".join(
        f"- Example {idx + 1}: {query}"
        for idx, query in enumerate(example_queries)
    )

    return {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a database expert. You will receive database schema information, example queries and a difficulty level. "
                    "Generate a new SQL query that matches the requested difficulty and can serve as a basis for creating exam questions. "
                    "The query should be correct, clear, didactic and structurally comparable to the examples, but not a copy. "
                    "You may think step by step internally before answering, but you must never write your reasoning, analysis or comments in the output. "
                    "Do not ask the user any questions. If something is unspecified, choose reasonable values yourself. "
                    "Your entire output must be exactly one valid SQL query formatted as <SQL>SELECT ...</SQL>. "
                    "Do not include anything else: no natural language text, no comments, no markdown code fences, "
                    "and no second <SQL>...</SQL> block."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Here is the schema for database {db_id}:\n"
                    f"Schema: {schema_desc}\n"
                    f"{pk_mapping_str}\n"
                    f"{foreign_keys}"
                )
            },
            {
                "role": "user",
                "content": (
                    f"Example queries for difficulty '{sql_difficulty}':\n"
                    f"{example_block}\n"
                    "Do not copy these verbatim—use them only as guidance for the structure and difficulty."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Now create a new SQL query with this difficulty: {sql_difficulty}. "
                    "Return only the SQL query wrapped in <SQL> and </SQL> with no additional text."
                )
            }
        ],
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 3000,
            "stop": ["</SQL>"]
        }
    }



# Hauptloop zum Generieren und Escapen aller Queries
extended_dataset = []

for data in dataset_list:
    # 1) Erzeuge Sets aller Spalten- und Tabellennamen
    column_names = {
        col.lower()
        for cols in data['column_types'].values()
        for col in cols.keys()
    }
    table_names = {
        tbl.lower()
        for tbl in data['column_types'].keys()
    }

    for _ in range(queries_per_db):
        data_copy = data.copy()

        # 2) Prompt generieren
        if prompt_type == 'standard':
            payload = generate_standard_prompt(data_copy, sql_difficulty)
        elif prompt_type == 'divide_and_conquer':
            payload = generate_divide_and_conquer_prompt(data_copy, sql_difficulty)
        elif prompt_type == 'query_plan':
            payload = generate_query_plan_prompt(data_copy, sql_difficulty)
        elif prompt_type == 'few_shot':
            payload = generate_few_shot_prompt(data_copy, sql_difficulty)
        else:
            # Fallback: standard
            payload = generate_standard_prompt(data_copy, sql_difficulty)

        # Prompt im Datensatz mit abspeichern
        data_copy["prompt"] = payload

        try:
            best_sql = None
            best_raw_output = None
            escape_error = None

            # Mehrfach versuchen, bis wir eine plausibel aussehende SQL-Query haben
            for attempt in range(1, MAX_ATTEMPTS_PER_QUERY + 1):
                output_message = call_ollama(payload)
                best_raw_output = output_message

                if not output_message.strip():
                    logging.warning(
                        f"No content from model in SQL-attempt {attempt}/{MAX_ATTEMPTS_PER_QUERY}."
                    )
                    continue

                raw_sql = extract_sql(output_message)
                if not is_plausible_sql(raw_sql):
                    logging.warning(
                        f"No plausible SQL found in attempt {attempt}/{MAX_ATTEMPTS_PER_QUERY}. "
                        f"Extracted: {raw_sql!r}"
                    )
                    continue

                # Wenn wir hier sind: raw_sql sieht ok aus -> escapen und fertig
                safe_sql, escape_error = escape_reserved_words(raw_sql, column_names, table_names)
                best_sql = safe_sql
                break  # aus dem for-Loop raus, Query steht

            if best_sql is None:
                # Alle Versuche gescheitert -> Datensatz als Fehler markieren
                data_copy["model_raw_output"] = best_raw_output or ""
                data_copy["generated_query"] = None
                data_copy["generation_error"] = "no_valid_sql_after_retries"
                extended_dataset.append(data_copy)
                logging.warning(
                    f"Skipping this sample: no valid SQL after {MAX_ATTEMPTS_PER_QUERY} attempts."
                )
                continue

            # Erfolg: best_sql enthält eine plausibel geparste Query
            data_copy["generated_query"] = best_sql
            if escape_error:
                data_copy["escape_reserved_words_error"] = escape_error

            extended_dataset.append(data_copy)
            logging.info(f"Generated safe query: {best_sql}")



        except Exception as e:
            logging.exception(f"Unexpected error when talking to Ollama: {e}")
            data_copy['generated_query'] = None
            extended_dataset.append(data_copy)

# 4) Ergebnis speichern
filename = f"model1_output_diff{difficulty_level}_prompt{prompt_type_code}"
if limit is not None:
    filename += f"_limit{limit}"
filename += ".json"

output_path = os.path.join(os.path.dirname(__file__), filename)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(extended_dataset, f, indent=2, ensure_ascii=False)

print(f"\n✅ Generierte Queries gespeichert in: {output_path}")

