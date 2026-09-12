"""Check canonical/legacy CLI entrypoints and preservation of migrated files."""
import argparse
import concurrent.futures
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as cwd:
        targets = [p for folder in ('data/tools', 'training/pretrain', 'training/evaluation', 'inference/cli', 'inference/export', 'inference/profiling', 'motionbricks/scripts')
                   for p in (ROOT / folder).glob('*.py') if p.name not in {'__init__.py', 'motion_batch_gate.py'}]
        def check(path):
            result = subprocess.run([sys.executable, str(path), '--help'], cwd=cwd, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=90)
            return {'script': str(path.relative_to(ROOT)), 'exit_code': result.returncode,
                    'help_present': ('usage:' in result.stdout.lower() or '用法' in result.stdout),
                    'error': result.stderr if result.returncode else ''}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            checks = list(pool.map(check, targets))
    report = {'outside_repository_cwd': True, 'cli_count': len(checks), 'cli': checks}
    audit = ROOT / '.build/repository-migration-20260912'
    if (audit / 'artifact-inventory.json').exists():
        moves = json.loads((audit / 'moves.json').read_text())
        inventories = json.loads((audit / 'artifact-inventory.json').read_text())
        changed = []
        count = 0
        for old, files in inventories.items():
            for name, expected in files.items():
                path = ROOT / moves[old] / name
                count += 1
                if not path.is_file() or [path.stat().st_size, path.stat().st_mtime_ns] != expected:
                    changed.append(str(path))
        report.update(artifact_files=count, artifact_metadata_changed=changed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    failures = [entry for entry in checks if entry['exit_code'] or not entry['help_present']]
    print(json.dumps({'cli_count': len(checks), 'failures': failures,
                      'artifact_files': report.get('artifact_files'), 'artifact_metadata_changed': report.get('artifact_metadata_changed')}, ensure_ascii=False))
    if failures or report.get('artifact_metadata_changed'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
