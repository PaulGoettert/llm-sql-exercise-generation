import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def build_snapshot(row, run_id):
    return {
        'run_id': run_id,
        'timestamp_utc': now_utc_iso(),
        'model2_action': row.get('model2_action'),
        'generated_query': row.get('generated_query'),
        'generation_error': row.get('generation_error'),
        'model_raw_output': row.get('model_raw_output'),
    }


def ensure_run_history(target):
    rh = target.get('run_history')
    if isinstance(rh, list):
        return rh
    target['run_history'] = []
    return target['run_history']


def snapshot_exists_for_run(run_history, run_id):
    for item in run_history:
        if isinstance(item, dict) and item.get('run_id') == run_id:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description='Merge model2 output back into canonical JSON using record_id (idempotent by run_id).'
    )
    parser.add_argument('--canonical-input', required=True)
    parser.add_argument('--model2-output', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--run-id', required=True, help='Stable run identifier used for idempotent merge/history.')
    args = parser.parse_args()

    canonical_path = Path(args.canonical_input)
    model2_path = Path(args.model2_output)
    output_path = Path(args.output)
    run_id = args.run_id

    canonical = load_json(canonical_path)
    model2_rows = load_json(model2_path)

    if not isinstance(canonical, list):
        raise ValueError('canonical-input must be a JSON list')
    if not isinstance(model2_rows, list):
        raise ValueError('model2-output must be a JSON list')

    canonical_by_id = {}
    for i, entry in enumerate(canonical):
        rid = entry.get('record_id')
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError(f'canonical entry {i} missing record_id')
        if rid in canonical_by_id:
            raise ValueError(f'duplicate record_id in canonical: {rid}')
        canonical_by_id[rid] = entry

    updates = 0
    missing_in_canonical = 0
    seen_model2_ids = set()
    skipped_existing_run = 0

    for i, row in enumerate(model2_rows):
        rid = row.get('record_id')
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError(f'model2 row {i} missing record_id')
        if rid in seen_model2_ids:
            raise ValueError(f'duplicate record_id in model2 output: {rid}')
        seen_model2_ids.add(rid)

        target = canonical_by_id.get(rid)
        if target is None:
            missing_in_canonical += 1
            continue

        # Keep original query immutable if already present.
        if not (isinstance(target.get('original_query'), str) and target.get('original_query').strip()):
            original_query = row.get('original_query')
            if isinstance(original_query, str) and original_query.strip():
                target['original_query'] = original_query

        run_history = ensure_run_history(target)
        if snapshot_exists_for_run(run_history, run_id):
            skipped_existing_run += 1
            continue

        snapshot = build_snapshot(row, run_id)
        run_history.append(snapshot)

        # Current fields for easy downstream consumption.
        target['generated_query'] = row.get('generated_query')
        target['model2_action'] = row.get('model2_action')
        target['generation_error'] = row.get('generation_error')
        target['model_raw_output'] = row.get('model_raw_output')
        target['last_run_id'] = run_id

        updates += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(canonical, f, ensure_ascii=False, indent=2)

    print(f'Canonical entries: {len(canonical)}')
    print(f'Model2 rows: {len(model2_rows)}')
    print(f'Updated entries: {updates}')
    print(f'Skipped (run_id already present): {skipped_existing_run}')
    print(f'Model2 rows without canonical match: {missing_in_canonical}')
    print(f'Wrote: {output_path}')


if __name__ == '__main__':
    main()
