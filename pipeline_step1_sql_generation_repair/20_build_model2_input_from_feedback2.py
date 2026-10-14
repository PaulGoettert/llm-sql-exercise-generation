import argparse
import importlib.util
import json
import pathlib
import re
from typing import Dict, Any


ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_FEEDBACK2_DIR = ROOT / 'analyse_feedback2'
DEFAULT_PROJECT_DIR = ROOT
DEFAULT_OUTPUT = ROOT / 'single_sql_dataset_from_feedback2.jsonl'

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


def parse_prompt_id(analysis_filename: str):
    m = re.search(r'(diff\d+_prompt\d+_limit\d+)', analysis_filename)
    return m.group(1) if m else None


def normalize_sql(sql_text):
    if not isinstance(sql_text, str):
        return ''
    s = sql_text.strip()
    if s.startswith('<SQL>') and s.endswith('</SQL>'):
        s = s[len('<SQL>'):-len('</SQL>')].strip()
    if s.endswith(';'):
        s = s[:-1].strip()
    return s.strip()


def wrap_sql(sql_text):
    return f"<SQL>{normalize_sql(sql_text)}</SQL>"


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


def load_module(path: pathlib.Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    parser = argparse.ArgumentParser(
        description='Build model2 input JSONL from analyse feedback2 only (deterministic reconstruction via project files).'
    )
    parser.add_argument('--feedback2-dir', default=str(DEFAULT_FEEDBACK2_DIR))
    parser.add_argument('--project-dir', default=str(DEFAULT_PROJECT_DIR), help='prep_step2_arctic_new_prompt directory')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT))
    parser.add_argument('--glob', default='step2_output_diff*_afterlint2.json')
    parser.add_argument('--expected-files', type=int, default=8)
    parser.add_argument('--expected-total', type=int, default=5600)
    args = parser.parse_args()

    feedback2_dir = pathlib.Path(args.feedback2_dir)
    project_dir = pathlib.Path(args.project_dir)
    output_path = pathlib.Path(args.output)

    resources_dir = project_dir / 'resources'
    analyse_dir = project_dir / 'analyse feedback'
    output2_dir = project_dir / 'output2'

    script06 = project_dir / '06_build_repair_prompts.py'
    repair_mod = load_module(script06, 'repair_builder_mod')

    files = sorted(feedback2_dir.glob(args.glob), key=lambda p: p.name)
    if len(files) != args.expected_files:
        raise ValueError(f'expected {args.expected_files} files, found {len(files)} in {feedback2_dir}')

    # Caches
    resources_cache: Dict[str, Any] = {}
    analyse_cache: Dict[str, Any] = {}
    output2_cache: Dict[str, Any] = {}

    rows = []
    missing_selected_source = 0
    missing_prompt_id = 0
    missing_resource_file = 0
    missing_analysis_file = 0
    missing_output2_file = 0

    for fb2_file in files:
        fb2_data = json.loads(fb2_file.read_text(encoding='utf-8'))
        analysis = fb2_data.get('analysis') if isinstance(fb2_data, dict) else None
        if not isinstance(analysis, list):
            raise ValueError(f'analysis missing in {fb2_file}')

        for j, entry in enumerate(analysis):
            if not isinstance(entry, dict):
                continue
            entry_index = entry.get('entry_index')
            if not isinstance(entry_index, int):
                entry_index = j

            selected_source = entry.get('selected_source_file')
            if not isinstance(selected_source, str) or not selected_source.strip():
                missing_selected_source += 1
                continue

            prompt_id = parse_prompt_id(selected_source)
            if not prompt_id:
                missing_prompt_id += 1
                continue

            source_file = f'model1_output_{prompt_id}.json'
            analysis_file = selected_source

            if source_file not in resources_cache:
                p = resources_dir / source_file
                if not p.exists():
                    missing_resource_file += 1
                    continue
                resources_cache[source_file] = json.loads(p.read_text(encoding='utf-8'))

            if analysis_file not in analyse_cache:
                p = analyse_dir / analysis_file
                if not p.exists():
                    missing_analysis_file += 1
                    continue
                analyse_cache[analysis_file] = json.loads(p.read_text(encoding='utf-8'))

            if analysis_file not in output2_cache:
                p = output2_dir / analysis_file
                if not p.exists():
                    missing_output2_file += 1
                    continue
                output2_cache[analysis_file] = json.loads(p.read_text(encoding='utf-8'))

            res_data = resources_cache[source_file]
            ana_data = analyse_cache[analysis_file]
            out2_data = output2_cache[analysis_file]

            if entry_index >= len(res_data):
                continue
            analysis_list = ana_data.get('analysis', []) if isinstance(ana_data, dict) else []
            if entry_index >= len(analysis_list):
                continue
            if entry_index >= len(out2_data):
                continue

            res_entry = res_data[entry_index]
            out2_entry = out2_data[entry_index] if isinstance(out2_data[entry_index], dict) else {}

            # Candidate/query chosen from feedback2 best-of result.
            candidate_sql = entry.get('query_text') or ''
            tests = entry.get('tests') or {}
            test_score = compute_test_score(tests)

            parse_validate_error = out2_entry.get('parse_validate_error') if isinstance(out2_entry, dict) else None
            if isinstance(parse_validate_error, str) and ':' in parse_validate_error:
                parse_validate_error = parse_validate_error.rsplit(':', 1)[-1]

            expected_diff = entry.get('expected_diff')
            if not isinstance(expected_diff, int):
                m = re.search(r'diff(\d+)', prompt_id)
                expected_diff = int(m.group(1)) if m else None

            record_id = entry.get('record_id')
            if not isinstance(record_id, str) or not record_id.strip():
                if isinstance(expected_diff, int):
                    record_id = f'diff{expected_diff}_entry{entry_index:04d}'
                else:
                    record_id = f'{prompt_id}_entry{entry_index:04d}'

            # Build entry in 06-script expected shape and reuse its prompt construction.
            reconstructed = {
                'db_id': f"{res_entry.get('db_id','')}_{pathlib.Path(source_file).stem}",
                'task_prompt': res_entry.get('prompt'),
                'candidate_sql': candidate_sql,
                'tests': tests,
                'meta': {
                    'source_file': source_file,
                    'analysis_file': analysis_file,
                    'entry_index': entry_index,
                    'prompt_id': prompt_id,
                    'run_id': prompt_id,
                },
            }
            if isinstance(parse_validate_error, str) and parse_validate_error.strip():
                reconstructed['parse_validate_error'] = parse_validate_error.strip()

            # This mutates reconstructed with repair_system_prompt + repair_prompt.
            repair_mod.add_repair_prompt(reconstructed)

            row = {
                'record_id': record_id,
                'expected_diff': expected_diff,
                'original_query': candidate_sql,
                # Keep structural fields required by step2 Java pipeline.
                'db_id': res_entry.get('db_id'),
                'column_types': res_entry.get('column_types'),
                'primary_keys': res_entry.get('primary_keys'),
                'sample_rows': res_entry.get('sample_rows'),
                'foreign_keys': res_entry.get('foreign_keys'),
                'model1_db_id': reconstructed.get('db_id'),
                'model1_system': reconstructed.get('repair_system_prompt') or '',
                'model1_prompt': reconstructed.get('repair_prompt') or '',
                'model1_sql_query': wrap_sql(candidate_sql),
                'model1_candidate_sql': candidate_sql,
                'model1_tests': tests,
                'model1_test_score': test_score,
                'model1_meta': reconstructed.get('meta'),
                'model1_task_prompt': reconstructed.get('task_prompt'),
            }
            row['system'] = row['model1_system']
            row['prompt'] = row['model1_prompt']
            row['sql_query'] = row['model1_sql_query']

            rows.append(row)

    if missing_selected_source > 0:
        raise ValueError(
            f'missing selected_source_file in {missing_selected_source} entries. '
            'Re-run updated combine_afterlint2.py first.'
        )

    if len(rows) != args.expected_total:
        raise ValueError(
            f'expected total {args.expected_total}, got {len(rows)} '\
            f'(missing prompt_id={missing_prompt_id}, resources={missing_resource_file}, analyse={missing_analysis_file}, output2={missing_output2_file})'
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    print(f'Wrote {len(rows)} rows to {output_path}')
    print(f'Missing selected_source_file: {missing_selected_source}')
    print(f'Missing prompt_id: {missing_prompt_id}')
    print(f'Missing resources files: {missing_resource_file}')
    print(f'Missing analyse files: {missing_analysis_file}')
    print(f'Missing output2 files: {missing_output2_file}')


if __name__ == '__main__':
    main()
