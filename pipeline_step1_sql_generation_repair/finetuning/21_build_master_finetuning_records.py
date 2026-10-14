from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path, PureWindowsPath
from typing import Dict, List, Tuple

FILE_RE = re.compile(r'^step2_output_diff(?P<diff>\d+)_prompt(?P<prompt>\d+)_limit(?P<limit>\d+)_after_lint\.json$')
WINDOWS_PATH_RE = re.compile(r'^[A-Za-z]:\\')


def normalize_path(value: str | Path) -> Path:
    text = str(value)
    if '\\' in text or WINDOWS_PATH_RE.match(text):
        win = PureWindowsPath(text)
        drive = win.drive.rstrip(':').lower()
        parts = list(win.parts[1:])
        return Path('/mnt') / drive / Path(*parts)
    return Path(text)


def load_json(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def parse_analysis_name(path: Path) -> Tuple[int, int, int]:
    match = FILE_RE.match(path.name)
    if not match:
        raise ValueError(f'unexpected analysis filename: {path.name}')
    return int(match.group('diff')), int(match.group('prompt')), int(match.group('limit'))


def make_paths(project_dir: Path, diff_id: int, prompt_id: int, limit: int) -> Dict[str, Path]:
    stem = f'diff{diff_id}_prompt{prompt_id}_limit{limit}'
    return {
        'resource': project_dir / 'resources' / f'model1_output_{stem}.json',
        'output': project_dir / 'output' / f'step2_output_{stem}.json',
        'output2': project_dir / 'output2' / f'step2_output_{stem}_after_lint.json',
        'analysis': project_dir / 'analyse feedback' / f'step2_output_{stem}_after_lint.json',
    }


def build_record(diff_id: int, prompt_id: int, limit: int, entry_index: int, resource_entry: dict, output_entry: dict, output2_entry: dict, analysis_entry: dict, source_files: Dict[str, str]) -> dict:
    db_id = resource_entry.get('db_id') or output_entry.get('db') or analysis_entry.get('db_id')
    tests = analysis_entry.get('tests') if isinstance(analysis_entry.get('tests'), dict) else {}
    query_text = analysis_entry.get('query_text') or output2_entry.get('query') or output_entry.get('query') or resource_entry.get('generated_query')

    return {
        'record_id': f'diff{diff_id}_prompt{prompt_id}_entry{entry_index:04d}',
        'expected_diff': diff_id,
        'prompt_number': prompt_id,
        'limit': limit,
        'entry_index': entry_index,
        'db_id': db_id,
        'query_text': query_text,
        'query_difficulty': output2_entry.get('query_difficulty', output_entry.get('query_difficulty')),
        'source_files': source_files,
        'resource': resource_entry,
        'step2_output': output_entry,
        'step2_output2': output2_entry,
        'analysis_feedback': analysis_entry,
        'summary_flags': {
            'test1_parse': bool(tests.get('test1_parse', {}).get('passed') is True),
            'test2_validate': bool(tests.get('test2_validate', {}).get('passed') is True),
            'test3_execution': bool(tests.get('test3_execution', {}).get('passed') is True),
            'test4_preview': bool(tests.get('test4_preview', {}).get('passed') is True),
            'test5_foreign_keys': bool(tests.get('test5_foreign_keys', {}).get('passed') is True),
            'test6_lint': bool(tests.get('test6_lint', {}).get('passed') is True),
            'test7_difficulty': bool(tests.get('test7_difficulty', {}).get('passed') is True),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Build a lossless raw master-record dataset for normal finetuning.')
    parser.add_argument('--project-dir', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--analysis-dir', default=None, help='Defaults to <project-dir>/analyse feedback')
    parser.add_argument('--output', default=None, help='Defaults to <project-dir>/finetuning/intermediate/master_finetuning_records_raw.json')
    parser.add_argument('--expected-files', type=int, default=32)
    parser.add_argument('--expected-total', type=int, default=22400)
    args = parser.parse_args()

    project_dir = normalize_path(args.project_dir)
    analysis_dir = normalize_path(args.analysis_dir) if args.analysis_dir else project_dir / 'analyse feedback'
    output_path = normalize_path(args.output) if args.output else project_dir / 'finetuning' / 'intermediate' / 'master_finetuning_records_raw.json'

    if not analysis_dir.exists():
        raise FileNotFoundError(f'analysis dir not found: {analysis_dir}')

    analysis_files = sorted(
        [p for p in analysis_dir.glob('step2_output_diff*_prompt*_limit*_after_lint.json') if FILE_RE.match(p.name)],
        key=parse_analysis_name,
    )
    if len(analysis_files) != args.expected_files:
        raise ValueError(f'expected {args.expected_files} analysis files, found {len(analysis_files)} in {analysis_dir}')

    records: List[dict] = []
    per_diff = Counter()
    per_prompt = Counter()

    for analysis_path in analysis_files:
        diff_id, prompt_id, limit = parse_analysis_name(analysis_path)
        paths = make_paths(project_dir, diff_id, prompt_id, limit)
        missing = [name for name, path in paths.items() if not path.exists()]
        if missing:
            raise FileNotFoundError(f'missing source files for {analysis_path.name}: {missing}')

        resource_data = load_json(paths['resource'])
        output_data = load_json(paths['output'])
        output2_data = load_json(paths['output2'])
        analysis_data = load_json(paths['analysis'])

        if not isinstance(resource_data, list):
            raise ValueError(f'resource file must be list: {paths["resource"]}')
        if not isinstance(output_data, list):
            raise ValueError(f'output file must be list: {paths["output"]}')
        if not isinstance(output2_data, list):
            raise ValueError(f'output2 file must be list: {paths["output2"]}')
        if not isinstance(analysis_data, dict) or not isinstance(analysis_data.get('analysis'), list):
            raise ValueError(f'analysis file must contain analysis list: {paths["analysis"]}')

        analysis_entries = analysis_data['analysis']
        lengths = {len(resource_data), len(output_data), len(output2_data), len(analysis_entries)}
        if len(lengths) != 1:
            raise ValueError(
                f'entry count mismatch for diff{diff_id} prompt{prompt_id}: '
                f'resources={len(resource_data)} output={len(output_data)} output2={len(output2_data)} analysis={len(analysis_entries)}'
            )

        source_files = {key: path.name for key, path in paths.items()}
        for idx, (resource_entry, output_entry, output2_entry, analysis_entry) in enumerate(zip(resource_data, output_data, output2_data, analysis_entries)):
            if not all(isinstance(x, dict) for x in (resource_entry, output_entry, output2_entry, analysis_entry)):
                raise ValueError(f'non-object entry at diff{diff_id} prompt{prompt_id} index {idx}')

            entry_index = analysis_entry.get('entry_index')
            if not isinstance(entry_index, int):
                entry_index = idx

            record = build_record(diff_id, prompt_id, limit, entry_index, resource_entry, output_entry, output2_entry, analysis_entry, source_files)
            records.append(record)
            per_diff[f'diff{diff_id}'] += 1
            per_prompt[f'prompt{prompt_id}'] += 1

    if len(records) != args.expected_total:
        raise ValueError(f'expected total {args.expected_total}, got {len(records)}')

    payload = {
        'schema_version': 1,
        'dataset_type': 'master_finetuning_records_raw',
        'project_dir': str(project_dir),
        'analysis_dir': str(analysis_dir),
        'total_entries': len(records),
        'per_diff_counts': dict(sorted(per_diff.items())),
        'per_prompt_counts': dict(sorted(per_prompt.items())),
        'records': records,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f'Wrote {len(records)} records to {output_path}')
    print(f'Per diff: {dict(sorted(per_diff.items()))}')
    print(f'Per prompt: {dict(sorted(per_prompt.items()))}')


if __name__ == '__main__':
    main()
