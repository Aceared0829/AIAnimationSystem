"""Measure sensitivity of Run contact coverage to the source speed threshold."""

import argparse
import base64
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.conditioned_motion import load_raw
from motionbricks.data.unreal_dataset import contained_file


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    contract_path = args.release / "contract" / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source = Path(contract["source_dataset"])
    skeleton = json.loads((source / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in
            ("left_foot", "left_toe", "right_foot", "right_toe")]
    starts = defaultdict(list)
    with (args.release / "contract" / "windows.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            clip = contract["clips"][row["clip_index"]]
            if clip["split"] == "validation" and clip["category"] == "Run":
                starts[row["clip_index"]].append(row["start"])
    thresholds = (0.15, 0.20, 0.30, 0.50)
    result = {f"{threshold:.2f}": {"all_clip_pairs": 0, "center_window_pairs": 0,
                                    "center_windows_without_pairs": 0,
                                    "center_by_speed_bin": {name: {"windows": 0, "pairs": 0, "without_pairs": 0}
                                                            for name in ("0-0.2", "0.2-1", "1-2", "2-4", "4+")}}
              for threshold in thresholds}
    n_center = 0
    for index, windows in starts.items():
        clip = contract["clips"][index]
        raw, _ = load_raw(contained_file(source, clip["raw_file"]), clip["source_frames"],
                          contract["bone_count"], contract["fps"], expected_sha256=clip["raw_sha256"])
        root = raw["root_track"]
        rotation = Rotation.from_quat(root[:, 3:]).as_matrix()
        world = np.einsum("tij,tkj->tki", rotation, raw["positions"][:, feet]) + root[:, None, :3]
        speed = np.linalg.norm(np.diff(world, axis=0), axis=-1) * contract["fps"]
        speed = np.concatenate((speed, speed[-1:]), axis=0)
        stored_bits = np.frombuffer(base64.b64decode(clip["contact_bits"]), dtype=np.uint8)
        stored = np.unpackbits(stored_bits)[:len(world) * 4].reshape(-1, 4).astype(bool)
        start = windows[len(windows) // 2]
        middle = start + contract["window"]["history_frames"]
        end = middle + contract["window"]["future_frames"]
        root_speed = np.linalg.norm(np.diff(root[middle - 1:end, :3], axis=0)[:, [0, 2]], axis=-1)
        mean_speed = float(root_speed.mean() * contract["fps"])
        speed_name = next(name for name, upper in (("0-0.2", 0.2), ("0.2-1", 1.0), ("1-2", 2.0),
                                                   ("2-4", 4.0), ("4+", float("inf"))) if mean_speed < upper)
        for threshold in thresholds:
            labels = (speed < threshold) & (world[:, :, 1] < 0.10)
            if threshold == 0.15 and not np.array_equal(labels, stored):
                raise ValueError(f"stored labels differ from threshold reimplementation at {index}")
            bucket = result[f"{threshold:.2f}"]
            bucket["all_clip_pairs"] += int((labels[1:] & labels[:-1]).sum())
            pairs = int((labels[middle + 1:end] & labels[middle:end - 1]).sum())
            bucket["center_window_pairs"] += pairs
            bucket["center_windows_without_pairs"] += int(pairs == 0)
            speed_bucket = bucket["center_by_speed_bin"][speed_name]
            speed_bucket["windows"] += 1
            speed_bucket["pairs"] += pairs
            speed_bucket["without_pairs"] += int(pairs == 0)
        n_center += 1
    output = {"schema_version": 1, "contract_sha256": sha256(contract_path),
              "split": "validation", "category": "Run", "clips": len(starts),
              "center_windows": n_center, "height_threshold_m": 0.10,
              "speed_thresholds_mps": result,
              "interpretation_boundary": "Threshold sensitivity only; additional pairs are not verified physical contacts."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
