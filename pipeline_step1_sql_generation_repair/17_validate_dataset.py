import argparse
import json
from pathlib import Path


def load_payload(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def get_records(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get('analysis'), list):
        return payload['analysis']
    raise ValueError('input must be either a JSON list or an object with list field "analysis"')


def parse_required_keys(raw: str):
    items = [x.strip() for x in raw.split(',') if x.strip()]
    return items


def get_nested(obj, dotted_key):
    cur = obj
    for part in dotted_key.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return None, False
        cur = cur[part]
    return cur, True


def main():
    parser = argparse.ArgumentParser(description='Validate dataset structure/count/id constraints.')
    parser.add_argument('--input', required=True, help='JSON file (list or {analysis:[...]})')
    parser.add_argument('--expected-count', type=int, default=None)
    parser.add_argument('--required-keys', default='record_id,expected_diff', help='Comma-separated keys. Supports dotted keys like tests.test7_difficulty.passed')
    parser.add_argument('--unique-key', default='record_id', help='Key that must be unique; empty disables uniqueness check')
    parser.add_argument('--allow-empty-values', action='store_true', help='If set, required keys may exist with null/empty values')
    args = parser.parse_args()

    path = Path(args.input)
    payload = load_payload(path)
    records = get_records(payload)

    required_keys = parse_required_keys(args.required_keys)

    errors = []

    if args.expected_count is not None and len(records) != args.expected_count:
        errors.append(f'count mismatch: expected {args.expected_count}, got {len(records)}')

    seen = set()
    duplicate_count = 0

    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            errors.append(f'entry {idx}: not an object')
            continue

        for key in required_keys:
            val, exists = get_nested(rec, key)
            if not exists:
                errors.append(f'entry {idx}: missing required key {key}')
                continue
            if not args.allow_empty_values:
                if val is None or (isinstance(val, str) and not val.strip()):
                    errors.append(f'entry {idx}: key {key} is empty')

        if args.unique_key:
            uval, exists = get_nested(rec, args.unique_key)
            if not exists:
                errors.append(f'entry {idx}: missing unique key {args.unique_key}')
            else:
                if uval in seen:
                    duplicate_count += 1
                else:
                    seen.add(uval)

    if duplicate_count > 0:
        errors.append(f'duplicate values for {args.unique_key}: {duplicate_count}')

    print(f'file: {path}')
    print(f'records: {len(records)}')
    print(f'required_keys: {required_keys}')
    print(f'unique_key: {args.unique_key if args.unique_key else "(disabled)"}')

    if errors:
        print('validation: FAILED')
        for err in errors[:50]:
            print(f'- {err}')
        if len(errors) > 50:
            print(f'- ... and {len(errors)-50} more errors')
        raise SystemExit(1)

    print('validation: OK')


if __name__ == '__main__':
    main()
