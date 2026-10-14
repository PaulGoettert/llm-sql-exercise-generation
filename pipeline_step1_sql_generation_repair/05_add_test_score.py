import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
IN_PATH = ROOT / 'master_records.json'
OUT_PATH = ROOT / 'master_records2.json'

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


def compute_test_score(entry):
    tests = entry.get('tests')
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


def main():
    data = json.loads(IN_PATH.read_text(encoding='utf-8'))
    for entry in data:
        entry['test_score'] = compute_test_score(entry)

    OUT_PATH.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding='utf-8')
    print(f'Wrote {len(data)} records to {OUT_PATH}')


if __name__ == '__main__':
    main()
