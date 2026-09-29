"""Count horizontal Root speeds in every frozen locomotion training/validation window."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from data.runtime.conditioned_motion import load_raw
from motionbricks.data.unreal_dataset import contained_file


CATEGORIES = {"Walk", "Run", "Crouch"}
BINS = (("0-0.2", 0.2), ("0.2-1", 1.0), ("1-2", 2.0), ("2-4", 4.0), ("4+", float("inf")))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def speed_bin(value):
    return next(name for name, upper in BINS if value < upper)


def audit(release, output):
    if output.exists():
        raise FileExistsError(output)
    contract_path = release / "contract" / "contract.json"
    windows_path = release / "contract" / "windows.jsonl"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source = Path(contract["source_dataset"])
    if sha256(source / "dataset.json") != contract["source_manifest_sha256"]:
        raise ValueError("source manifest differs from frozen contract")
    by_clip = defaultdict(list)
    with windows_path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            clip = contract["clips"][row["clip_index"]]
            if clip["category"] in CATEGORIES and clip["split"] in ("train", "validation"):
                by_clip[row["clip_index"]].append(row["start"])
    counts = defaultdict(Counter)
    clip_counts = defaultdict(lambda: defaultdict(set))
    steady_counts = defaultdict(Counter)
    history = contract["window"]["history_frames"]
    future = contract["window"]["future_frames"]
    for number, (index, starts) in enumerate(sorted(by_clip.items()), 1):
        clip = contract["clips"][index]
        raw, _ = load_raw(contained_file(source, clip["raw_file"]), clip["source_frames"],
                          contract["bone_count"], contract["fps"], expected_sha256=clip["raw_sha256"])
        root = raw["root_track"]
        speed = np.linalg.norm(np.diff(root[:, [0, 2]], axis=0), axis=-1) * contract["fps"]
        for start in starts:
            motion = speed[start + history - 1:start + history + future - 1]
            if len(motion) != future:
                raise ValueError(f"window out of range: {index}, {start}")
            name = speed_bin(float(motion.mean()))
            key = (clip["split"], clip["category"])
            counts[key][name] += 1
            clip_counts[key][name].add(index)
            if float(motion.std()) < 0.10:
                steady_counts[key][name] += 1
        if number % 200 == 0:
            print(f"loaded {number}/{len(by_clip)} locomotion clips", flush=True)
    rows = []
    for split in ("train", "validation"):
        for category in ("Walk", "Run", "Crouch"):
            key = (split, category)
            for name, _ in BINS:
                rows.append({"split": split, "category": category, "speed_bin_mps": name,
                             "windows": counts[key][name], "distinct_clips": len(clip_counts[key][name]),
                             "steady_windows": steady_counts[key][name]})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema_version": 1, "contract_sha256": sha256(contract_path),
                                  "windows_sha256": sha256(windows_path), "fps": contract["fps"],
                                  "history_frames": history, "future_frames": future,
                                  "speed_definition": "mean horizontal source Root speed across the 24 future frames; includes first history-to-future step",
                                  "steady_definition": "within-window speed standard deviation <0.10 m/s",
                                  "bins": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.release, args.output)


if __name__ == "__main__":
    main()
