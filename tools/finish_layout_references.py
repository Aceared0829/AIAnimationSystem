"""Mechanical remaining path substitutions in the current usage documentation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = list((ROOT / 'docs/motionbricks').glob('*.md')) + list((ROOT / 'unreal-script').rglob('*.md'))
paths += [ROOT / 'docs/project-background.md']
replacements = {
    'motionbricks/requirements-unreal-training.txt': 'training/requirements.txt',
    'motionbricks/unreal_data/': 'data/prepared/',
    'motionbricks/unreal_runs/': 'training/runs/',
    'motionbricks/tests': 'tests',
    '--no-deps -e motionbricks': '--no-deps -e .',
    'cd AIAnimationSystem/motionbricks': 'cd AIAnimationSystem',
    'pip install -e .': 'pip install -e ".[training,demo]"',
    'src="assets/': 'src="../../inference/assets/',
    'ls -lh out/': 'ls -lh model-weight/base/motionbricks/',
    '`out/`': '`model-weight/base/motionbricks/`',
}
for path in paths:
    if not path.exists():
        continue
    text = path.read_text(encoding='utf-8')
    original = text
    for old, new in replacements.items():
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding='utf-8')
