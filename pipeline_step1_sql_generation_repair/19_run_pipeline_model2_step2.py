import argparse
import json
import shutil
import subprocess
from pathlib import Path


def run_cmd(cmd, cwd=None):
    print('[CMD]', ' '.join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def call_manifest(script18, run_id, stage, manifest_out, input_files=None, output_files=None, notes=''):
    input_files = input_files or []
    output_files = output_files or []
    cmd = [
        'python3', str(script18),
        '--run-id', run_id,
        '--stage', stage,
        '--manifest-out', str(manifest_out),
        '--notes', notes,
    ]
    if input_files:
        cmd += ['--input-files', *[str(p) for p in input_files]]
    if output_files:
        cmd += ['--output-files', *[str(p) for p in output_files]]
    run_cmd(cmd)


def jsonl_to_canonical_json(jsonl_path: Path, canonical_json_path: Path):
    rows = []
    with jsonl_path.open('r', encoding='utf-8') as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            row = json.loads(s)
            # Keep model1 payload and add aliases expected by validators/analyzers.
            if 'candidate_sql' not in row:
                row['candidate_sql'] = row.get('model1_candidate_sql', '')
            if 'test_score' not in row:
                row['test_score'] = row.get('model1_test_score', {})
            rows.append(row)

    canonical_json_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description='Run end-to-end model2 + step2 pipeline with validation and manifests.')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--canonical-input', help='Canonical JSON input (list with record_id/expected_diff). If omitted, built from --feedback2-dir via script 20.')
    parser.add_argument('--canonical-merged-output', required=True, help='Merged canonical JSON after model2.')
    parser.add_argument('--single-sql-output', default='single_sql_dataset.jsonl')
    parser.add_argument('--model2-output', default='model2_output_all_limit140.json')
    parser.add_argument('--resources-target', required=True, help='Target JSON path under step2/src/main/resources/model1_output*.json')
    parser.add_argument('--expected-count', type=int, default=5600)

    parser.add_argument('--repo-root', default=str(pathlib.Path(__file__).resolve().parents[1]))
    parser.add_argument('--prep-root', default=str(pathlib.Path(__file__).resolve().parent))

    parser.add_argument('--feedback2-dir', default=str(pathlib.Path(__file__).resolve().parent / 'analyse_feedback2'), help='Used when --canonical-input is omitted.')
    parser.add_argument('--model2-input-builder', default='20_build_model2_input_from_feedback2.py', help='Script in prep root to build model2 JSONL from feedback2.')

    parser.add_argument('--skip-model2', action='store_true', help='Skip model2.py call (use existing --model2-output).')
    parser.add_argument('--skip-step2', action='store_true', help='Skip mvn + augment + analyze + combine stage.')

    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    prep_root = Path(args.prep_root)
    code_root = repo_root / 'code'
    step2_root = code_root / 'sql-analyzer' / 'step2'

    canonical_merged = Path(args.canonical_merged_output)
    single_sql_output = prep_root / args.single_sql_output
    model2_output = prep_root / args.model2_output
    resources_target = Path(args.resources_target)

    script12 = prep_root / '12_build_single_sql_dataset.py'
    script16 = prep_root / '16_merge_model2_back_by_record_id.py'
    script17 = prep_root / '17_validate_dataset.py'
    script18 = prep_root / '18_write_run_manifest.py'
    script20 = prep_root / args.model2_input_builder
    script_model2 = prep_root / 'model2.py'

    augment_script = code_root / 'augment_sqllint.py'
    analyze_script = code_root / 'analyze_step2_outputs.py'
    combine_script = code_root / 'combine_afterlint2.py'

    manifest_dir = prep_root / 'run_manifests'
    manifest_dir.mkdir(parents=True, exist_ok=True)

    # Build or load canonical input
    if args.canonical_input:
        canonical_input = Path(args.canonical_input)
        # Stage 2: Build single_sql_dataset from canonical
        run_cmd([
            'python3', str(script12),
            '--input', str(canonical_input),
            '--output', str(single_sql_output),
        ])
        call_manifest(
            script18,
            args.run_id,
            'build_single_sql_dataset',
            manifest_dir / f'{args.run_id}_02_build_single_sql.json',
            input_files=[canonical_input],
            output_files=[single_sql_output],
        )
    else:
        # Build model2 input directly from feedback2, then derive canonical JSON from that JSONL.
        feedback2_dir = Path(args.feedback2_dir)
        run_cmd([
            'python3', str(script20),
            '--feedback2-dir', str(feedback2_dir),
            '--project-dir', str(prep_root),
            '--output', str(single_sql_output),
            '--expected-total', str(args.expected_count),
        ])
        canonical_input = prep_root / f'canonical_from_feedback2_{args.run_id}.json'
        row_count = jsonl_to_canonical_json(single_sql_output, canonical_input)
        if row_count != args.expected_count:
            raise ValueError(f'expected {args.expected_count} rows from feedback2 build, got {row_count}')

        call_manifest(
            script18,
            args.run_id,
            'build_from_feedback2',
            manifest_dir / f'{args.run_id}_02_build_from_feedback2.json',
            input_files=[],
            output_files=[single_sql_output, canonical_input],
            notes='model2 JSONL and canonical JSON reconstructed from analyse feedback2',
        )

    # Stage 1: Validate canonical input
    run_cmd([
        'python3', str(script17),
        '--input', str(canonical_input),
        '--expected-count', str(args.expected_count),
        '--required-keys', 'record_id,expected_diff,candidate_sql,test_score.score,db_id,column_types,primary_keys,sample_rows',
        '--unique-key', 'record_id',
    ])
    call_manifest(
        script18,
        args.run_id,
        'validate_canonical_input',
        manifest_dir / f'{args.run_id}_01_validate_input.json',
        input_files=[canonical_input],
        notes='validated canonical input before model2'
    )

    # Stage 3: Run model2 (optional)
    if args.skip_model2:
        if not model2_output.exists():
            raise FileNotFoundError(
                f'--skip-model2 set, but model2 output file not found: {model2_output}. '
                'Either run without --skip-model2 or point --model2-output to an existing file.'
            )
    else:
        run_cmd(['python3', str(script_model2)], cwd=prep_root)
        if not model2_output.exists():
            raise FileNotFoundError(f'model2 run finished but output file not found: {model2_output}')
    call_manifest(
        script18,
        args.run_id,
        'model2_output',
        manifest_dir / f'{args.run_id}_03_model2_output.json',
        input_files=[single_sql_output],
        output_files=[model2_output],
        notes='model2 stage (or reused existing model2 output if skipped)'
    )

    # Stage 4: Merge model2 back into canonical (idempotent by run_id)
    run_cmd([
        'python3', str(script16),
        '--canonical-input', str(canonical_input),
        '--model2-output', str(model2_output),
        '--output', str(canonical_merged),
        '--run-id', args.run_id,
    ])
    run_cmd([
        'python3', str(script17),
        '--input', str(canonical_merged),
        '--expected-count', str(args.expected_count),
        '--required-keys', 'record_id,expected_diff,original_query,generated_query,model2_action',
        '--unique-key', 'record_id',
        '--allow-empty-values',
    ])
    call_manifest(
        script18,
        args.run_id,
        'merge_model2_back',
        manifest_dir / f'{args.run_id}_04_merge_back.json',
        input_files=[canonical_input, model2_output],
        output_files=[canonical_merged],
    )

    # Stage 5: Copy merged file into step2 resources target
    resources_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(canonical_merged, resources_target)
    call_manifest(
        script18,
        args.run_id,
        'copy_to_step2_resources',
        manifest_dir / f'{args.run_id}_05_copy_to_resources.json',
        input_files=[canonical_merged],
        output_files=[resources_target],
    )

    if args.skip_step2:
        print('skip-step2 enabled: skipping mvn/augment/analyze/combine stage')
        return

    # Stage 6: Step2 + lint + analysis + combine
    run_cmd(['mvn', 'clean', 'compile', 'exec:java'], cwd=step2_root)
    run_cmd([
        'python3', str(augment_script),
        '--outputs-dir', 'sql-analyzer/step2/output',
        '--dest-dir', 'sql-analyzer/step2/output2',
        '--suffix', '_after_lint',
    ], cwd=code_root)
    run_cmd(['python3', str(analyze_script)], cwd=code_root)
    run_cmd(['python3', str(combine_script)], cwd=code_root)

    call_manifest(
        script18,
        args.run_id,
        'step2_pipeline_complete',
        manifest_dir / f'{args.run_id}_06_step2_pipeline.json',
        input_files=[resources_target],
        output_files=[step2_root / 'analyse feedback2' / 'step2_output_diff1_afterlint2.json'],
        notes='final stage marker; output_files contains a representative artifact',
    )

    print('Pipeline completed successfully.')


if __name__ == '__main__':
    main()


