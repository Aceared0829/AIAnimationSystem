"""Fetch the upstream G1 Pose weight in bounded HTTP ranges and verify the Git LFS identity."""
import concurrent.futures
import hashlib
import re
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELATIVE = 'model-weight/base/motionbricks/motionbricks_pose/version_1/checkpoints/model-step=2000000.ckpt'
URL = 'https://media.githubusercontent.com/media/NVlabs/GR00T-WholeBodyControl/main/motionbricks/out/motionbricks_pose/version_1/checkpoints/model-step=2000000.ckpt'


def main():
    pointer = subprocess.check_output(['git', 'show', ':' + RELATIVE], cwd=ROOT).decode('ascii')
    digest = re.search(r'oid sha256:([a-f0-9]{64})', pointer).group(1)
    size = int(re.search(r'size (\d+)', pointer).group(1))
    destination = ROOT / RELATIVE
    if destination.stat().st_size > 1024:
        raise RuntimeError('Destination is already materialized; refusing to overwrite it')
    work = ROOT / '.build/g1-pose-download'
    work.mkdir(parents=True, exist_ok=True)
    chunk_size = 32 * 1024 * 1024
    chunks = [(index, start, min(start + chunk_size, size) - 1) for index, start in enumerate(range(0, size, chunk_size))]
    def download(chunk):
        index, start, end = chunk
        path = work / f'{index:03d}.part'
        if path.exists() and path.stat().st_size == end - start + 1:
            return path
        for attempt in range(5):
            offset = path.stat().st_size if path.exists() else 0
            if offset == end - start + 1:
                break
            begin = start + offset
            request = urllib.request.Request(URL, headers={'Range': f'bytes={begin}-{end}', 'User-Agent': 'AIAnimationSystem-weight-setup'})
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    if response.status != 206 or response.headers.get('Content-Range') != f'bytes {begin}-{end}/{size}':
                        raise RuntimeError(f'Unexpected range response for chunk {index}')
                    with path.open('ab') as stream:
                        while block := response.read(1024 * 1024):
                            stream.write(block)
            except (OSError, TimeoutError):
                print(f'Retrying chunk {index + 1}, attempt {attempt + 1}', flush=True)
                time.sleep(1)
        if path.stat().st_size != end - start + 1:
            raise RuntimeError(f'Incomplete chunk {index}; rerun to resume')
        print(f'chunk {index + 1}/{len(chunks)} verified length', flush=True)
        return path
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        parts = list(pool.map(download, chunks))
    assembled = work / 'verified.ckpt'
    calculated = hashlib.sha256()
    with assembled.open('wb') as target:
        for path in parts:
            with path.open('rb') as source:
                while block := source.read(8 * 1024 * 1024):
                    target.write(block)
                    calculated.update(block)
    if assembled.stat().st_size != size or calculated.hexdigest() != digest:
        raise RuntimeError('Weight does not match the committed Git LFS SHA-256')
    if not destination.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1'):
        raise RuntimeError('Destination changed during download')
    assembled.replace(destination)
    print(f'PASS: {size} bytes, SHA-256 {digest}', flush=True)


if __name__ == '__main__':
    main()
