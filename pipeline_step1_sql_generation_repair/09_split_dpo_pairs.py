import json
import pathlib
import random
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent
PAIRS_IN = ROOT / 'dpo_pairs_final.jsonl'
DEBUG_IN = ROOT / 'dpo_pairs_final_debug.jsonl'

TRAIN_OUT = ROOT / 'train_dpo.jsonl'
VAL_OUT = ROOT / 'val_dpo.jsonl'
TEST_OUT = ROOT / 'test_dpo.jsonl'

TRAIN_DEBUG_OUT = ROOT / 'train_dpo_debug.jsonl'
VAL_DEBUG_OUT = ROOT / 'val_dpo_debug.jsonl'
TEST_DEBUG_OUT = ROOT / 'test_dpo_debug.jsonl'

REPORT_OUT = ROOT / 'split_report.json'

SEED = 42
TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10


def base_db_from_group_id(group_id):
    if not isinstance(group_id, str):
        raise ValueError('group_id missing or not a string')
    token = '_model1_output_'
    if token in group_id:
        return group_id.split(token)[0]
    return group_id


def main():
    if not DEBUG_IN.exists():
        raise ValueError('Debug file missing: cannot split without group_id')

    pair_lines = PAIRS_IN.read_text(encoding='utf-8').splitlines()
    debug_lines = DEBUG_IN.read_text(encoding='utf-8').splitlines()

    if len(pair_lines) != len(debug_lines):
        raise ValueError('Pair/debug line count mismatch')

    base_dbs = []
    for d_line in debug_lines:
        debug = json.loads(d_line)
        group_id = debug.get('group_id')
        base_dbs.append(base_db_from_group_id(group_id))

    unique_base = sorted(set(base_dbs))
    rng = random.Random(SEED)
    rng.shuffle(unique_base)

    n = len(unique_base)
    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)
    train_set = set(unique_base[:n_train])
    val_set = set(unique_base[n_train:n_train + n_val])
    test_set = set(unique_base[n_train + n_val:])

    if train_set & val_set or train_set & test_set or val_set & test_set:
        raise ValueError('Split sets are not disjoint')

    counts = Counter()
    base_counts = Counter()

    with TRAIN_OUT.open('w', encoding='utf-8') as tr, \
        VAL_OUT.open('w', encoding='utf-8') as va, \
        TEST_OUT.open('w', encoding='utf-8') as te, \
        TRAIN_DEBUG_OUT.open('w', encoding='utf-8') as trd, \
        VAL_DEBUG_OUT.open('w', encoding='utf-8') as vad, \
        TEST_DEBUG_OUT.open('w', encoding='utf-8') as ted:

        for p_line, d_line, base_db in zip(pair_lines, debug_lines, base_dbs):
            if base_db in train_set:
                tr.write(p_line + '\n')
                trd.write(d_line + '\n')
                counts['train_pairs'] += 1
                base_counts['train_base'] += 1
            elif base_db in val_set:
                va.write(p_line + '\n')
                vad.write(d_line + '\n')
                counts['val_pairs'] += 1
                base_counts['val_base'] += 1
            elif base_db in test_set:
                te.write(p_line + '\n')
                ted.write(d_line + '\n')
                counts['test_pairs'] += 1
                base_counts['test_base'] += 1
            else:
                raise ValueError('Base DB not in any split set')

    report = {
        'seed': SEED,
        'ratios': {'train': TRAIN_RATIO, 'val': VAL_RATIO, 'test': TEST_RATIO},
        'pairs': dict(counts),
        'distinct_base_db': {
            'train': len(train_set),
            'val': len(val_set),
            'test': len(test_set),
        },
        'base_db_sets': {
            'train': sorted(train_set),
            'val': sorted(val_set),
            'test': sorted(test_set),
        },
    }

    REPORT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
