import json
import pathlib
import hashlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent
PAIRS_IN = ROOT / 'dpo_pairs.jsonl'
DEBUG_IN = ROOT / 'dpo_pairs_debug.jsonl'
PAIRS_OUT = ROOT / 'dpo_pairs_final.jsonl'
DEBUG_OUT = ROOT / 'dpo_pairs_final_debug.jsonl'
REPORT_OUT = ROOT / 'report.json'

MIN_DELTA = 6
CHOSEN_SCORE_MIN = 36


def sha1_key(system, prompt, chosen, rejected):
    payload = f'{system}\n{prompt}\n{chosen}\n{rejected}'
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()


def has_sql_wrapper(sql_text):
    if not isinstance(sql_text, str):
        return False
    s = sql_text.strip()
    return s.startswith('<SQL>') and s.endswith('</SQL>')


def sanity_checks(pair):
    system = pair.get('system', '')
    prompt = pair.get('prompt', '')
    chosen = pair.get('chosen', '')
    rejected = pair.get('rejected', '')

    if not chosen or not rejected:
        return False
    if chosen == rejected:
        return False
    if not has_sql_wrapper(chosen) or not has_sql_wrapper(rejected):
        return False
    if '`' in chosen or '`' in rejected:
        return False
    if 'CANDIDATE SQL:' not in prompt:
        return False
    if rejected not in prompt:
        return False

    return True


def get_required_debug(debug):
    required = [
        'group_id',
        'chosen_score',
        'rejected_score',
        'chosen_hard_flags_ok',
        'rejected_hard_flags_ok',
    ]
    for key in required:
        if key not in debug:
            raise ValueError(f'Missing debug field: {key}')
    return debug


def main():
    pairs_lines = PAIRS_IN.read_text(encoding='utf-8').splitlines()
    debug_lines = DEBUG_IN.read_text(encoding='utf-8').splitlines()

    if len(pairs_lines) != len(debug_lines):
        raise ValueError('Input JSONL files have different line counts')

    input_count = len(pairs_lines)
    after_chosen_quality = 0
    after_delta = 0
    after_dedupe = 0
    num_duplicates_removed = 0

    deltas = []
    chosen_scores = Counter()
    rejected_scores = Counter()
    seen = set()

    with PAIRS_OUT.open('w', encoding='utf-8') as pairs_out, DEBUG_OUT.open('w', encoding='utf-8') as debug_out:
        for i, (p_line, d_line) in enumerate(zip(pairs_lines, debug_lines), start=1):
            pair = json.loads(p_line)
            debug = json.loads(d_line)
            debug = get_required_debug(debug)

            if not sanity_checks(pair):
                continue

            chosen_score = int(debug['chosen_score'])
            rejected_score = int(debug['rejected_score'])

            if not debug['chosen_hard_flags_ok']:
                continue
            if chosen_score < CHOSEN_SCORE_MIN:
                continue
            after_chosen_quality += 1

            delta = chosen_score - rejected_score
            if delta < MIN_DELTA:
                continue
            after_delta += 1

            key = sha1_key(pair.get('system', ''), pair.get('prompt', ''), pair.get('chosen', ''), pair.get('rejected', ''))
            if key in seen:
                num_duplicates_removed += 1
                continue
            seen.add(key)

            after_dedupe += 1
            deltas.append(delta)
            chosen_scores[chosen_score] += 1
            rejected_scores[rejected_score] += 1

            pairs_out.write(json.dumps(pair, ensure_ascii=False) + '\n')
            debug_out.write(json.dumps(debug, ensure_ascii=False) + '\n')

    if deltas:
        deltas_sorted = sorted(deltas)
        mid = len(deltas_sorted) // 2
        if len(deltas_sorted) % 2 == 1:
            delta_median = deltas_sorted[mid]
        else:
            delta_median = (deltas_sorted[mid - 1] + deltas_sorted[mid]) / 2
        delta_min = deltas_sorted[0]
        delta_max = deltas_sorted[-1]
    else:
        delta_min = delta_median = delta_max = None

    report = {
        'input_count': input_count,
        'after_chosen_quality_count': after_chosen_quality,
        'after_delta_count': after_delta,
        'after_dedupe_count': after_dedupe,
        'num_duplicates_removed': num_duplicates_removed,
        'delta_min': delta_min,
        'delta_median': delta_median,
        'delta_max': delta_max,
        'chosen_score_distribution': dict(chosen_scores),
        'rejected_score_distribution': dict(rejected_scores),
    }

    REPORT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
