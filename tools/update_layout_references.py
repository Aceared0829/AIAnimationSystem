"""Mechanical documentation path updates for the recorded repository migration."""
import json
import posixpath
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / '.build/repository-migration-20260912'
moves = json.loads((AUDIT / 'moves.json').read_text())
scripts = json.loads((AUDIT / 'scripts.json').read_text())


def destination(path):
    for source, target in moves.items():
        if path == source or path.startswith(source + '/'):
            path = target + path[len(source):]
    return path


tracked = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'ls-files'], cwd=ROOT).decode('utf-8').splitlines()
for old in tracked:
    new = destination(old)
    path = ROOT / new
    if path.suffix != '.md' or not path.exists():
        continue
    text = path.read_text(encoding='utf-8-sig')
    original = text
    def link(match):
        label, url = match.groups()
        if '://' in url or url.startswith(('#', 'mailto:')):
            return match.group(0)
        target, separator, anchor = url.partition('#')
        old_target = posixpath.normpath(posixpath.join(posixpath.dirname(old), target))
        new_target = destination(old_target)
        if (ROOT / new_target).exists():
            url = posixpath.relpath(new_target, posixpath.dirname(new) or '.') + (separator + anchor if separator else '')
        return f'[{label}]({url})'
    text = re.sub(r'\[([^\]]*)\]\(([^)]+)\)', link, text)
    # Inline paths and shell examples are rooted at the checkout after this migration.
    for name, target in scripts.items():
        text = text.replace(f'motionbricks/scripts/{name}.py', target)
        text = re.sub(rf'(?<![\w/])scripts/{name}\.py', target, text)
    for source, target in sorted(moves.items(), key=lambda pair: -len(pair[0])):
        if source.startswith(('model/', 'data/', 'training/')):
            continue
        text = text.replace('`' + source, '`' + destination(source))
        text = text.replace('"' + source + '/', '"' + destination(source) + '/')
    text = text.replace('cd motionbricks\n', '# 以下命令在仓库根目录执行\n')
    if new == '.agents/skills/process-motion-batches/SKILL.md':
        text = text.replace('`motionbricks/scripts`', '`data/tools`（宿主内脚本在 `unreal-script/python`）')
    if text != original:
        path.write_text(text, encoding='utf-8')

print('Updated tracked Markdown links and canonical command paths.')
