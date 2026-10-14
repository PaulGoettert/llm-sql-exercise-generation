from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
from collections import defaultdict
from typing import Any, Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_MASTER = ROOT / 'intermediate' / 'master_finetuning_records_raw.json'
DEFAULT_OUTPUT = ROOT / 'output' / 'train_finetuning_axolotl_chatml.jsonl'
DEFAULT_REPORT = ROOT / 'output' / 'train_finetuning_axolotl_chatml_report.json'

WEIGHTS = {
    'test1_parse': 3,
    'test2_validate': 5,
    'test3_execution': 12,
    'test5_foreign_keys': 6,
    'test6_lint': 4,
    'test7_difficulty': 6,
    'test4_preview': 1,
}
MANDATORY = ['test1_parse', 'test2_validate', 'test3_execution', 'test7_difficulty']


def load_module(path: pathlib.Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def compute_test_score(tests):
    score = 0
    if isinstance(tests, dict):
        for name, weight in WEIGHTS.items():
            t = tests.get(name)
            passed = t.get('passed') if isinstance(t, dict) else None
            if passed is True:
                score += weight
    else:
        tests = {}

    hard_flags_ok = True
    for name in MANDATORY:
        t = tests.get(name)
        passed = t.get('passed') if isinstance(t, dict) else None
        if passed is not True:
            hard_flags_ok = False
            break
    return {'score': score, 'hard_flags_ok': hard_flags_ok}


def normalize_sql(sql_text: str) -> str:
    if not isinstance(sql_text, str):
        return ''
    s = sql_text.strip()
    if s.startswith('<SQL>') and s.endswith('</SQL>'):
        s = s[len('<SQL>'):-len('</SQL>')].strip()
    if s.endswith(';'):
        s = s[:-1].strip()
    return s


def wrap_sql(sql_text: str) -> str:
    return f'<SQL>{normalize_sql(sql_text)}</SQL>'


def build_repair_entry(master_record: Dict[str, Any]) -> Dict[str, Any]:
    resource = master_record.get('resource') or {}
    analysis = master_record.get('analysis_feedback') or {}
    tests = analysis.get('tests') or {}
    query = resource.get('generated_query') or master_record.get('query_text') or ''

    prompt_number = master_record.get('prompt_number')
    expected_diff = master_record.get('expected_diff')
    limit = master_record.get('limit')
    prompt_id = None
    if isinstance(expected_diff, int) and isinstance(prompt_number, int) and isinstance(limit, int):
        prompt_id = f'diff{expected_diff}_prompt{prompt_number}_limit{limit}'

    return {
        'record_id': master_record.get('record_id'),
        'expected_diff': expected_diff,
        'candidate_sql': query,
        'task_prompt': resource.get('prompt'),
        'tests': tests,
        'meta': {
            'prompt_id': prompt_id,
            'run_id': prompt_id,
            'entry_index': master_record.get('entry_index'),
            'source_files': master_record.get('source_files'),
        },
    }


def group_key(record: Dict[str, Any]) -> Tuple[int, int, str]:
    return (
        int(record.get('expected_diff')),
        int(record.get('prompt_number')),
        str(record.get('db_id') or ''),
    )


def choose_target(record: Dict[str, Any]) -> Tuple[int, str]:
    entry_index = record.get('entry_index')
    if not isinstance(entry_index, int):
        entry_index = 10**9
    return (entry_index, str(record.get('record_id') or ''))


def main() -> None:
    parser = argparse.ArgumentParser(description='Build final Axolotl SFT repair dataset directly from raw master records.')
    parser.add_argument('--input', default=str(DEFAULT_MASTER))
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT))
    parser.add_argument('--report', default=str(DEFAULT_REPORT))
    parser.add_argument('--required-score', type=int, default=37)
    args = parser.parse_args()

    in_path = pathlib.Path(args.input)
    out_path = pathlib.Path(args.output)
    report_path = pathlib.Path(args.report)

    project_root = ROOT.parent
    script06 = project_root / '06_build_repair_prompts.py'
    repair_mod = load_module(script06, 'repair_prompt_builder_mod')

    payload = json.loads(in_path.read_text(encoding='utf-8'))
    records = payload.get('records') if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError('input must be master dataset object with list field "records"')

    grouped: Dict[Tuple[int, int, str], List[Dict[str, Any]]] = defaultdict(list)
    score_counter: Dict[int, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        tests = (record.get('analysis_feedback') or {}).get('tests') or {}
        test_score = compute_test_score(tests)
        record['_score'] = test_score['score']
        score_counter[test_score['score']] = score_counter.get(test_score['score'], 0) + 1
        grouped[group_key(record)].append(record)

    rows = []
    duplicate_prompt_count = 0
    groups_with_perfect = 0
    faulty_candidates = 0
    seen_prompts = set()

    for key, group_records in grouped.items():
        perfect = [r for r in group_records if r.get('_score') == args.required_score]
        faulty = [r for r in group_records if r.get('_score') != args.required_score]
        if not perfect or not faulty:
            continue

        groups_with_perfect += 1
        perfect_target = sorted(perfect, key=choose_target)[0]
        target_query = normalize_sql((perfect_target.get('resource') or {}).get('generated_query') or '')
        if not target_query:
            continue

        for faulty_record in sorted(faulty, key=choose_target):
            faulty_candidates += 1
            repair_entry = build_repair_entry(faulty_record)
            repair_mod.add_repair_prompt(repair_entry)

            system = repair_entry.get('repair_system_prompt') or ''
            prompt = repair_entry.get('repair_prompt') or ''
            if not prompt.strip():
                continue

            if prompt in seen_prompts:
                duplicate_prompt_count += 1
                continue
            seen_prompts.add(prompt)

            rows.append({
                'record_id': faulty_record.get('record_id'),
                'target_record_id': perfect_target.get('record_id'),
                'db_id': faulty_record.get('db_id'),
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': prompt},
                    {'role': 'assistant', 'content': wrap_sql(target_query)},
                ],
            })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    report = {
        'input': str(in_path),
        'output': str(out_path),
        'required_score': args.required_score,
        'input_records': len(records),
        'score_distribution': dict(sorted(score_counter.items())),
        'groups_total': len(grouped),
        'groups_with_perfect_and_faulty': groups_with_perfect,
        'faulty_candidates_before_prompt_dedup': faulty_candidates,
        'duplicate_prompts_removed': duplicate_prompt_count,
        'final_records': len(rows),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'Wrote {len(rows)} rows to {out_path}')
    print(f'Groups with perfect+faulty: {groups_with_perfect}')
    print(f'Faulty candidates before prompt dedup: {faulty_candidates}')
    print(f'Duplicate prompts removed: {duplicate_prompt_count}')
    print(f'Report: {report_path}')


if __name__ == '__main__':
    main()
