import json
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
IN_PATH = ROOT / 'master_records2.json'
OUT_PATH = ROOT / 'master_records2_with_repair_prompt.json'

TEST_ORDER = [
    'test1_parse',
    'test2_validate',
    'test3_execution',
    'test7_difficulty',
    'test5_foreign_keys',
    'test6_lint',
    'test4_preview',
]

DIFFICULTY_DEFINITIONS = {
    "diff1": "simple SQL statements with a single table, without JOIN and without aggregation, only with WHERE",
    "diff2": "SQL statements with JOIN without aggregation (monotone queries)",
    "diff3": "SQL statements with NOT EXISTS or NOT IN without aggregation (non-monotone queries)",
    "diff4": "SQL statements with aggregation functions without GROUP BY",
    "diff5": "SQL statements with aggregation functions with GROUP BY",
    "diff6": "SQL statements with aggregation functions with GROUP BY and HAVING",
    "diff7": "SQL statements with UNION and LEFT JOIN",
    "diff8": "SQL statements with LEFT JOIN and aggregation with GROUP BY, count including zero results",
}

REPAIR_SYSTEM_PROMPT = (
    "You are an SQL query repair expert: you receive a database schema with a target difficulty, "
    "a faulty candidate SQL query, and explicit test feedback describing the errors; return exactly one corrected SQL query "
    "wrapped in <SQL>...</SQL> with no explanation, comments, or markdown."
)

TEST_NAME_LABELS = {
    'test1_parse': 'test1_parse',
    'test2_validate': 'test2_validate',
    'test3_execution': 'test3_execution',
    'test4_preview': 'test4_preview',
    'test5_foreign_keys': 'test5_foreign_keys',
    'test6_lint': 'test6_query_semantic_errors',
    'test7_difficulty': 'test7_difficulty',
}


def extract_system_user(messages):
    system_prompt = ''
    user_task = ''

    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get('role')
            content = msg.get('content', '')
            if role == 'system' and system_prompt == '':
                system_prompt = content or ''
            elif role == 'user' and user_task == '':
                user_task = content or ''
            if system_prompt and user_task:
                break

    return system_prompt, user_task


def extract_difficulty_label(entry):
    meta = entry.get('meta') if isinstance(entry, dict) else None
    if isinstance(meta, dict):
        for key in ('prompt_id', 'run_id'):
            value = meta.get(key)
            if isinstance(value, str):
                m = re.search(r'(diff\d+)', value)
                if m:
                    return m.group(1)
    return 'unknown'


def wrap_sql(sql_text):
    if not isinstance(sql_text, str):
        sql_text = ''
    stripped = sql_text.strip()
    if stripped.startswith('<SQL>') and stripped.endswith('</SQL>'):
        return stripped
    return f'<SQL>{stripped}</SQL>'


def normalize_diff_label(value):
    if isinstance(value, int):
        if 1 <= value <= 8:
            return f'diff{value}'
        return None
    if isinstance(value, str):
        s = value.strip().lower()
        if s.startswith('diff') and s[4:].isdigit():
            return s
        if s.isdigit():
            n = int(s)
            if 1 <= n <= 8:
                return f'diff{n}'
    return None


def format_diff_label(label):
    text = DIFFICULTY_DEFINITIONS.get(label)
    if text:
        return f'{label} ({text})'
    return label or 'unknown'


def format_difficulty_detail(detail):
    if isinstance(detail, dict):
        expected = normalize_diff_label(detail.get('expected'))
        actual = normalize_diff_label(detail.get('actual_diff'))
        if expected or actual:
            exp_text = format_diff_label(expected) if expected else 'unknown'
            act_text = format_diff_label(actual) if actual else 'unknown'
            return f'expected {exp_text}; got {act_text}'
    if isinstance(detail, (dict, list)):
        return json.dumps(detail, ensure_ascii=False, separators=(',', ':'))
    if detail is None:
        return 'failed'
    return str(detail)


def build_failed_report(tests, parse_validate_error):
    if not isinstance(tests, dict):
        return '- (tests missing)'

    lines = []
    for name in TEST_ORDER:
        t = tests.get(name)
        passed = t.get('passed') if isinstance(t, dict) else None
        if passed is False:
            detail = t.get('detail') if isinstance(t, dict) else None
            if name == 'test7_difficulty':
                detail_text = format_difficulty_detail(detail)
            elif isinstance(detail, str):
                detail_text = detail
            elif isinstance(detail, (dict, list)):
                detail_text = json.dumps(detail, ensure_ascii=False, separators=(',', ':'))
            elif detail is None:
                detail_text = 'failed'
            else:
                detail_text = str(detail)
            if name == 'test1_parse' and parse_validate_error:
                if detail_text == 'parsed_sql missing or empty' or detail_text == 'failed':
                    detail_text = parse_validate_error
            test_label = TEST_NAME_LABELS.get(name, name)
            lines.append(f'- {test_label}: FAIL - {detail_text}'.rstrip())

    if not lines:
        return '- (no failed tests)'

    return '\n'.join(lines)


def add_repair_prompt(entry):
    task_prompt = entry.get('task_prompt', {}) if isinstance(entry, dict) else {}
    messages = task_prompt.get('messages') if isinstance(task_prompt, dict) else None
    _system_prompt, user_task = extract_system_user(messages)
    difficulty_label = extract_difficulty_label(entry)

    candidate_sql = entry.get('candidate_sql') if isinstance(entry, dict) else ''
    if candidate_sql is None:
        candidate_sql = ''
    wrapped_sql = wrap_sql(candidate_sql)

    tests = entry.get('tests') if isinstance(entry, dict) else None
    pve = entry.get('parse_validate_error') if isinstance(entry, dict) else ''
    if not isinstance(pve, str):
        pve = ''
    report = build_failed_report(tests, pve)

    difficulty_text = DIFFICULTY_DEFINITIONS.get(difficulty_label)
    if difficulty_text:
        difficulty_block = f"- {difficulty_label[-1]}: {difficulty_text}\n"
    else:
        difficulty_block = "- unknown: difficulty label not found\n"

    parts = [
        'CONTEXT (single sentence):',
        'You are given a database schema and target difficulty, plus a faulty candidate SQL query and explicit test feedback describing its errors.',
        '',
        'TASK (schema + requirements):',
        f'{user_task}\n',
        'REQUESTED DIFFICULTY:',
        f'{difficulty_label}',
        'Difficulty definitions:',
        difficulty_block,
        'SQL DIALECT:',
        '- Use standard SQL compatible with SQLite execution.',
        '- Do not use backticks `...` for identifiers.',
        '',
    ]
    if pve.strip():
        parts.extend([
            'PARSER/VALIDATION ERROR (highest priority):',
            pve.strip(),
            'Fix this first: use ONLY tables/columns that exist in the provided schema.',
            '',
        ])
    parts.extend([
        'CANDIDATE SQL:',
        wrapped_sql,
        '',
        'TARGET CHECKLIST:',
        '- Must be valid for the schema (existing tables/columns only)',
        '- Must execute successfully',
        '- Must match the requested difficulty/constraints',
        '- If JOIN is used: join predicates must follow listed foreign keys',
        '- Must have no query semantic errors',
        '- Output must be EXACTLY one SQL query wrapped in <SQL>...</SQL>',
        '',
        'FAILED TESTS (root-cause first):',
        report,
        '',
        'OUTPUT:',
        'Return ONLY the corrected SQL query wrapped in <SQL>...</SQL>. No explanation. No comments. No markdown.',
    ])
    repair_prompt = '\n'.join(parts).strip() + '\n'

    entry['repair_system_prompt'] = REPAIR_SYSTEM_PROMPT
    entry['repair_prompt'] = repair_prompt
    return entry


def main():
    data = json.loads(IN_PATH.read_text(encoding='utf-8'))
    for entry in data:
        add_repair_prompt(entry)

    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {len(data)} records to {OUT_PATH}')


if __name__ == '__main__':
    main()
