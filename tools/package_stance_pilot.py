"""打包站蹲试验输入；运行环境需提供兼容的 MotionBricks 基础包。"""

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path

from data.runtime.conditioned_motion import sha256
from motionbricks.data.unreal_dataset import contained_file, read_json


PROJECT = Path(__file__).resolve().parents[1]


def add_file(archive, source, name, hashes):
    source = Path(source)
    data = source.read_bytes()
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o644
    archive.addfile(info, io.BytesIO(data))
    hashes[name] = hashlib.sha256(data).hexdigest()


def package(stance_folder, base_folder, source_folder, checkpoint, output):
    stance_folder, base_folder, source_folder = (Path(value).resolve() for value in
                                                 (stance_folder, base_folder, source_folder))
    checkpoint, output = Path(checkpoint).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"训练包已存在：{output}")
    stance, base = read_json(stance_folder / "contract.json"), read_json(base_folder / "contract.json")
    if stance["base_contract_sha256"] != sha256(base_folder / "contract.json"):
        raise ValueError("来源 v1 契约哈希不匹配")
    if sha256(source_folder / "dataset.json") != stance["source_manifest_sha256"]:
        raise ValueError("来源清单哈希不匹配")
    if sha256(source_folder / "skeleton.json") != stance["skeleton_sha256"]:
        raise ValueError("来源骨架哈希不匹配")
    for key in ("mean", "std"):
        stats = base["stats"]["pose_m"]
        if sha256(base_folder / "stats" / stats[key]) != stats[f"{key}_sha256"]:
            raise ValueError("姿态统计量哈希不匹配")
    sources = []
    for annotation in stance["annotations"]:
        clip = base["clips"][annotation["clip_index"]]
        raw = contained_file(source_folder, clip["raw_file"])
        if sha256(raw) != clip["raw_sha256"]:
            raise ValueError(f"来源动作哈希不匹配：{raw}")
        sources.append((raw, f"bundle/source/{clip['raw_file']}"))
    code_roots = ("data", "model", "training", "inference", "tests", "tools")
    code = [(path, f"bundle/project/{path.relative_to(PROJECT).as_posix()}")
            for root in code_roots for path in (PROJECT / root).rglob("*.py")
            if "__pycache__" not in path.parts]
    code += [(PROJECT / name, f"bundle/project/{name}") for name in ("setup.py", "pyproject.toml")]
    files = (code + [(stance_folder / "contract.json", "bundle/stance/contract.json"),
                     (stance_folder / "windows.jsonl", "bundle/stance/windows.jsonl"),
                     (base_folder / "contract.json", "bundle/base/contract.json"),
                     (source_folder / "dataset.json", "bundle/source/dataset.json"),
                     (source_folder / "skeleton.json", "bundle/source/skeleton.json"),
                     (checkpoint, "bundle/weights/parent.pt")]
             + [(base_folder / "stats" / base["stats"]["pose_m"][key],
                 f"bundle/base/stats/{base['stats']['pose_m'][key]}") for key in ("mean", "std")]
             + sources)
    hashes = {}
    with tarfile.open(output, "w:gz") as archive:
        for path, name in sorted(files, key=lambda item: item[1]):
            add_file(archive, path, name, hashes)
        manifest = {"format": "stance_pilot_bundle_v1", "stance_contract_sha256": sha256(stance_folder / "contract.json"),
                    "base_contract_sha256": stance["base_contract_sha256"],
                    "checkpoint_sha256": sha256(checkpoint), "members_sha256": hashes,
                    "remote_overrides": {"stance_contract": "bundle/stance", "base_contract": "bundle/base",
                                         "source_dataset": "bundle/source", "initialize_from": "bundle/weights/parent.pt"}}
        info = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        member = tarfile.TarInfo("bundle/manifest.json")
        member.size = len(info)
        member.mode = 0o644
        archive.addfile(member, io.BytesIO(info))
    with tarfile.open(output, "r:gz") as archive:
        actual = {member.name: hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                  for member in archive.getmembers() if member.isfile() and member.name != "bundle/manifest.json"}
    if actual != hashes:
        raise ValueError("训练包回读哈希与输入不一致")
    return {"archive": str(output), "archive_sha256": sha256(output), "files": len(hashes),
            "bytes": output.stat().st_size, "stance_contract_sha256": manifest["stance_contract_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stance-contract", required=True)
    parser.add_argument("--base-contract", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.stance_contract, args.base_contract, args.source, args.checkpoint,
                             args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
