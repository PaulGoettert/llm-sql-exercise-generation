import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def count_records(path: Path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and isinstance(data.get('analysis'), list):
        return len(data['analysis'])
    return None


def git_commit(repo_root: Path):
    try:
        out = subprocess.check_output(['git', '-C', str(repo_root), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
        return out
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description='Write run manifest with file hashes/counts and metadata.')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--stage', required=True, help='e.g. combine_afterlint2, model2_input, model2_output, step2_output')
    parser.add_argument('--input-files', nargs='*', default=[])
    parser.add_argument('--output-files', nargs='*', default=[])
    parser.add_argument('--notes', default='')
    parser.add_argument('--manifest-out', required=True)
    parser.add_argument('--repo-root', default=str(pathlib.Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    repo_root = Path(args.repo_root)

    def file_info(pstr):
        p = Path(pstr)
        if not p.exists():
            return {'path': str(p), 'exists': False}
        return {
            'path': str(p),
            'exists': True,
            'size_bytes': p.stat().st_size,
            'sha256': sha256_file(p),
            'record_count': count_records(p),
        }

    manifest = {
        'run_id': args.run_id,
        'stage': args.stage,
        'timestamp_utc': ts,
        'git_commit': git_commit(repo_root),
        'notes': args.notes,
        'inputs': [file_info(x) for x in args.input_files],
        'outputs': [file_info(x) for x in args.output_files],
    }

    out = Path(args.manifest_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote manifest: {out}')


if __name__ == '__main__':
    main()

