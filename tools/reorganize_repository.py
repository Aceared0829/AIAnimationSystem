"""One-time, non-overwriting responsibility-layout migration. Run from this checkout."""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / '.build' / 'repository-migration-20260912'


def inside(relative):
    path = ROOT / relative
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError(f'Outside workspace: {path}')
    return path


def move(source, target):
    source, target = inside(source), inside(target)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))


def main():
    if AUDIT.exists():
        raise RuntimeError('Migration receipt already exists; do not rerun')
    AUDIT.mkdir(parents=True)
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).decode('utf-8')
    (AUDIT / 'status-before.txt').write_text(status, encoding='utf-8')
    # Preserve the bytes of every pre-existing user edit before path rewrites.
    for line in status.splitlines():
        source = ROOT / line[3:]
        if source.is_file():
            backup = AUDIT / 'user-edits' / line[3:]
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup)

    scripts = {}
    for path in (ROOT / 'motionbricks/scripts').glob('*.py'):
        name = path.stem
        if name.startswith('train_'):
            target = 'training/pretrain'
        elif name.startswith(('evaluate_', 'diagnose_', 'export_native_gallery', 'export_vq_gallery')):
            target = 'training/evaluation'
        elif name == 'export_unreal_inference':
            target = 'inference/export'
        elif name == 'profile_unreal_inference':
            target = 'inference/profiling'
        elif name == 'interactive_demo_g1':
            target = 'inference/cli'
        else:
            target = 'data/tools'
        scripts[name] = f'{target}/{path.name}'

    moves = {
        'motionbricks/motionbricks': 'model/motionbricks',
        'model/motionbricks/data': 'data/runtime',
        'model/motionbricks/vqvae/models': 'training/models/vqvae',
        'model/motionbricks/motion_backbone/models': 'training/models/backbone',
        'model/motionbricks/motionlib/train': 'training/common/optim',
        'model/motionbricks/motion_backbone/inference': 'inference/runtime/backbone',
        'model/motionbricks/motion_backbone/demo': 'inference/demo',
        'model/motionbricks/exp_setup': 'inference/runtime/experiment',
        'data/runtime/unreal_quality.py': 'training/common/unreal_quality.py',
        'training/models/backbone/sampling.py': 'model/motionbricks/motion_backbone/sampling.py',
        'motionbricks/assets': 'inference/assets',
        'motionbricks/configs': 'training/configs',
        'motionbricks/out': 'model-weight/base/motionbricks',
        'motionbricks/unreal_data': 'data/prepared',
        'motionbricks/unreal_runs': 'training/runs',
        'motionbricks/scripts/unreal': 'unreal-script/python',
        'motionbricks/scripts/review_web': 'data/tools/review_web',
        'Unreal/AILocomotionSystem': 'unreal-script/AILocomotionSystem',
        'motionbricks/tests': 'tests',
        'motionbricks/docs': 'docs/motionbricks',
        'motionbricks/README.md': 'docs/motionbricks/README.md',
        'motionbricks/requirements-unreal-training.txt': 'training/requirements.txt',
    }
    moves.update({f'motionbricks/scripts/{name}.py': target for name, target in scripts.items()})
    # Count and retain size/mtime inventories of local data and checkpoints; move on the same volume.
    inventories = {}
    for directory in ('motionbricks/unreal_data', 'motionbricks/unreal_runs', 'motionbricks/out'):
        inventories[directory] = {str(p.relative_to(ROOT / directory)): (p.stat().st_size, p.stat().st_mtime_ns)
                                  for p in (ROOT / directory).rglob('*') if p.is_file()}
    (AUDIT / 'artifact-inventory.json').write_text(json.dumps(inventories), encoding='utf-8')
    for source, target in moves.items():
        move(source, target)
    for source, inventory in inventories.items():
        target = ROOT / moves[source]
        observed = {str(p.relative_to(target)): (p.stat().st_size, p.stat().st_mtime_ns)
                    for p in target.rglob('*') if p.is_file()}
        if observed != inventory:
            raise RuntimeError(f'Artifact inventory changed: {source}')

    packages = ['data', 'data/tools', 'training', 'training/pretrain', 'training/posttrain',
                'training/evaluation', 'training/common', 'training/models', 'inference',
                'inference/cli', 'inference/export', 'inference/profiling', 'inference/runtime']
    for package in packages:
        directory = ROOT / package
        directory.mkdir(parents=True, exist_ok=True)
        (directory / '__init__.py').touch(exist_ok=True)

    # Mechanical import updates: explicit packages replace same-directory script imports.
    text_files = []
    for folder in ('data', 'training', 'model', 'inference', 'tests', 'unreal-script'):
        for p in (ROOT / folder).rglob('*.py'):
            if any(part in {'runs', 'prepared', '__pycache__', 'Binaries', 'Intermediate'} for part in p.parts):
                continue
            text_files.append(p)
    for path in text_files:
        text = path.read_text(encoding='utf-8-sig')
        original = text
        for name, target in scripts.items():
            module = target[:-3].replace('/', '.')
            text = re.sub(rf'(?m)^from {name} import ', f'from {module} import ', text)
        text = text.replace('from motionbricks.motion_backbone.models.sampling import ',
                            'from motionbricks.motion_backbone.sampling import ')
        text = text.replace('motionbricks.data.unreal_quality', 'motionbricks.training.unreal_quality')
        # Tests execute the canonical entries, including subprocess training.
        for name, target in scripts.items():
            text = re.sub(r'Path\(__file__\)\.resolve\(\)\.parents\[1\]\s*/\s*[\'\"]scripts[\'\"]\s*/\s*[\'\"]' + name + r'\.py[\'\"]',
                          f'Path(__file__).resolve().parents[1] / "{target}"', text)
            text = re.sub(r'Path\(__file__\)\.resolve\(\)\.parents\[1\]\s*/\s*[\'\"]scripts/' + name + r'\.py[\'\"]',
                          f'Path(__file__).resolve().parents[1] / "{target}"', text)
        text = re.sub(r"(?m)^sys.path.insert\(0,\s*str\(Path\(__file__\).resolve\(\).parents\[1\]\s*/\s*'scripts'\)\)\s*$", '', text)
        text = text.replace('SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"\nsys.path.insert(0, str(SCRIPTS))\n', '')
        if text != original:
            path.write_text(text, encoding='utf-8')

    # Old executable/script entrypoints remain small delegates, without duplicate implementation.
    for name, target in scripts.items():
        module = target[:-3].replace('/', '.')
        wrapper = ROOT / f'motionbricks/scripts/{name}.py'
        wrapper.write_text(f'"""Compatibility entry; use {target}."""\nimport runpy\n\n'
                           f'if __name__ == "__main__":\n    runpy.run_module("{module}", run_name="__main__")\n'
                           f'else:\n    from {module} import *\n', encoding='utf-8')
    (AUDIT / 'moves.json').write_text(json.dumps(moves, indent=2), encoding='utf-8')
    (AUDIT / 'scripts.json').write_text(json.dumps(scripts, indent=2), encoding='utf-8')
    print(json.dumps({'moved': len(moves), 'artifact_files_preserved': sum(map(len, inventories.values()))}))


if __name__ == '__main__':
    main()
