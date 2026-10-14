import json
import pathlib
import re
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent
IN_PATH = ROOT / 'master_records2_with_repair_prompt.json'
OUT_PATH = ROOT / 'dpo_pairs.jsonl'
DEBUG_PATH = ROOT / 'dpo_pairs_debug.jsonl'

MIN_DELTA = 6
MAX_TOKENS = 3000


def get_system(entry):
    repair_system = entry.get('repair_system_prompt') if isinstance(entry, dict) else None
    if isinstance(repair_system, str) and repair_system.strip():
        return repair_system

    task_prompt = entry.get('task_prompt', {}) if isinstance(entry, dict) else {}
    messages = task_prompt.get('messages') if isinstance(task_prompt, dict) else None
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict) and msg.get('role') == 'system':
                return msg.get('content', '') or ''
    return ''


def get_score(entry):
    test_score = entry.get('test_score') if isinstance(entry, dict) else None
    if isinstance(test_score, dict):
        return int(test_score.get('score') or 0)
    return 0


def normalize_sql(sql_text):
    if not isinstance(sql_text, str):
        sql_text = ''
    stripped = sql_text.strip()
    if stripped.startswith('<SQL>') and stripped.endswith('</SQL>'):
        stripped = stripped[len('<SQL>'):-len('</SQL>')].strip()
    return stripped.replace('`', '').strip()


def wrap_sql(inner_sql):
    return f'<SQL>{inner_sql}</SQL>'


def normalize_and_wrap(sql_text):
    return wrap_sql(normalize_sql(sql_text))


def is_chosen_candidate(entry):
    required = [
        'test1_parse',
        'test2_validate',
        'test3_execution',
        'test5_foreign_keys',
        'test6_lint',
        'test7_difficulty',
    ]
    for name in required:
        if not t_passed(entry, name):
            return False
    return True


def t_passed(entry, name):
    tests = entry.get('tests') if isinstance(entry, dict) else None
    if isinstance(tests, dict):
        t = tests.get(name)
        if isinstance(t, dict):
            return t.get('passed') is True
    return False


def update_prompt_candidate_sql(prompt, new_sql):
    if not isinstance(prompt, str):
        return None
    start_token = 'CANDIDATE SQL:\n'
    end_token = '\n\nTARGET CHECKLIST:'
    start_idx = prompt.find(start_token)
    if start_idx == -1:
        return None
    start_idx += len(start_token)
    end_idx = prompt.find(end_token, start_idx)
    if end_idx == -1:
        return None
    return prompt[:start_idx] + new_sql + prompt[end_idx:]


def estimate_tokens(text):
    if not isinstance(text, str):
        return 0
    return len(re.findall(r'\S+', text))


def entry_token_count(entry):
    parts = [
        entry.get('system', ''),
        entry.get('prompt', ''),
        entry.get('chosen', ''),
        entry.get('rejected', ''),
    ]
    return sum(estimate_tokens(part) for part in parts)


def pick_chosen(group_entries):
    candidates = [e for e in group_entries if is_chosen_candidate(e)]
    if not candidates:
        return None

    def key_fn(e):
        return (
            get_score(e),
            t_passed(e, 'test5_foreign_keys'),
            t_passed(e, 'test6_lint'),
            t_passed(e, 'test4_preview'),
        )

    best = candidates[0]
    best_key = key_fn(best)
    for e in candidates[1:]:
        k = key_fn(e)
        if k > best_key:
            best = e
            best_key = k
    return best


def pick_rejects(group_entries, chosen, min_delta):
    chosen_score = get_score(chosen)
    chosen_sql = chosen.get('candidate_sql') or ''
    chosen_norm = normalize_sql(chosen_sql)

    others = [e for e in group_entries if e is not chosen]
    others.sort(key=get_score)

    rejects = []
    for e in others:
        if len(rejects) >= 2:
            break
        cand_score = get_score(e)
        if chosen_score - cand_score < min_delta:
            continue
        cand_sql = e.get('candidate_sql') or ''
        cand_norm = normalize_sql(cand_sql)
        if not cand_norm:
            continue
        if cand_sql == chosen_sql:
            continue
        if cand_norm == chosen_norm:
            continue
        repair_prompt = e.get('repair_prompt')
        if not isinstance(repair_prompt, str) or not repair_prompt.strip():
            continue
        rejects.append(e)

    return rejects


def build_pairs_for_group(group_entries):
    pairs = []
    chosen = pick_chosen(group_entries)
    if chosen is None:
        return pairs

    rejects = pick_rejects(group_entries, chosen, MIN_DELTA)
    for rej in rejects:
        chosen_sql = normalize_and_wrap(chosen.get('candidate_sql') or '')
        rejected_sql = normalize_and_wrap(rej.get('candidate_sql') or '')
        if not normalize_sql(chosen_sql) or not normalize_sql(rejected_sql):
            continue
        if normalize_sql(chosen_sql) == normalize_sql(rejected_sql):
            continue
        prompt = update_prompt_candidate_sql(rej.get('repair_prompt'), rejected_sql)
        if prompt is None:
            continue
        pair = {
            'system': get_system(rej),
            'prompt': prompt,
            'chosen': chosen_sql,
            'rejected': rejected_sql,
        }
        if entry_token_count(pair) > MAX_TOKENS:
            continue
        debug = {
            'group_id': rej.get('db_id'),
            'chosen_score': get_score(chosen),
            'rejected_score': get_score(rej),
            'chosen_hard_flags_ok': is_chosen_candidate(chosen),
            'rejected_hard_flags_ok': is_chosen_candidate(rej),
            'prompt_id': (rej.get('meta') or {}).get('prompt_id'),
            'run_id': (rej.get('meta') or {}).get('run_id'),
        }
        pairs.append((pair, debug))

    return pairs


def main():
    data = json.loads(IN_PATH.read_text(encoding='utf-8'))
    groups = defaultdict(list)
    for entry in data:
        group_id = entry.get('db_id')
        groups[group_id].append(entry)

    with OUT_PATH.open('w', encoding='utf-8') as out_f, DEBUG_PATH.open('w', encoding='utf-8') as dbg_f:
        total = 0
        for group_entries in groups.values():
            pairs = build_pairs_for_group(group_entries)
            for pair, debug in pairs:
                out_f.write(json.dumps(pair, ensure_ascii=False) + '\n')
                dbg_f.write(json.dumps(debug, ensure_ascii=False) + '\n')
                total += 1

    print(f'Wrote {total} pairs to {OUT_PATH} (debug: {DEBUG_PATH})')


if __name__ == '__main__':
    main()
