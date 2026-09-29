"""Explain contact-label sparsity in the 30 frozen diagnostic clips.

All alternative thresholds are sensitivity probes, not ground-truth contacts.
The script reads source clips with their frozen SHA-256 checks and writes no
changes to the release or Motion Review decisions.
"""

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.conditioned_motion import load_raw
from motionbricks.data.unreal_dataset import contained_file


FOOT_ROLES = ("left_foot", "left_toe", "right_foot", "right_toe")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def count_pairs(label):
    return int((label[1:] & label[:-1]).sum())


def inspect(release, baseline, queue, output):
    contract_path = release / "contract" / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source = Path(contract["source_dataset"])
    for name, expected in (("dataset.json", contract["source_manifest_sha256"]),
                           ("skeleton.json", contract["skeleton_sha256"])):
        if sha256(source / name) != expected:
            raise ValueError(f"Frozen source changed: {name}")
    skeleton = json.loads((source / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in FOOT_ROLES]
    with queue.open(newline="", encoding="utf-8-sig") as stream:
        candidates = list(csv.DictReader(stream))
    with baseline.open(newline="", encoding="utf-8-sig") as stream:
        centers = {int(row["clip_index"]): row for row in csv.DictReader(stream)
                   if row["model"] == "generated_contact10"}
    if len(candidates) != 30 or len({int(row["clip_index"]) for row in candidates}) != 30:
        raise ValueError("Expected 30 unique frozen review candidates")
    rows = []
    for candidate in candidates:
        index = int(candidate["clip_index"])
        clip = contract["clips"][index]
        center = centers[index]
        if candidate["asset"] != clip["asset"]:
            raise ValueError(f"Candidate asset mismatch at {index}")
        raw, _ = load_raw(contained_file(source, clip["raw_file"]), clip["source_frames"],
                          contract["bone_count"], contract["fps"],
                          expected_sha256=clip["raw_sha256"])
        root = raw["root_track"]
        world = np.einsum("tij,tkj->tki", Rotation.from_quat(root[:, 3:]).as_matrix(),
                          raw["positions"][:, feet]) + root[:, None, :3]
        velocity = np.linalg.norm(np.diff(world, axis=0), axis=-1) * contract["fps"]
        velocity = np.concatenate((velocity, velocity[-1:]), axis=0)
        height = world[:, :, 1]
        floor = np.quantile(height, .05, axis=0)
        low_speed = velocity < .15
        low_height = height < .10
        stored = low_speed & low_height
        import base64
        bits = np.unpackbits(np.frombuffer(base64.b64decode(clip["contact_bits"], validate=True),
                                         dtype=np.uint8))[:len(world) * 4].reshape(-1, 4).astype(bool)
        if not np.array_equal(stored, bits):
            raise ValueError(f"Stored contact mismatch at {index}")
        start = int(center["start"])
        middle = start + contract["window"]["history_frames"]
        end = middle + contract["window"]["future_frames"]
        if count_pairs(bits[middle:end]) != int(candidate["contact_pairs"]):
            raise ValueError(f"Center contact-pair mismatch at {index}")
        sl = slice(middle, end)
        slow = low_speed[sl]
        low = low_height[sl]
        local = height[sl] < floor[None] + .10
        loose_speed = velocity[sl] < .30
        root_speed = np.linalg.norm(np.diff(root[middle - 1:end, :3], axis=0)[:, [0, 2]], axis=-1) * contract["fps"]
        row = {
            "clip_index": index, "category": clip["category"], "asset": clip["asset"],
            "source_frames": len(world), "center_start": middle, "center_end_exclusive": end,
            "center_root_speed_mps": round(float(root_speed.mean()), 4),
            "stored_center_pairs": count_pairs(bits[sl]),
            "full_clip_stored_pairs": count_pairs(bits),
            "center_contact_bits": int(bits[sl].sum()),
            "center_low_speed_bits": int(slow.sum()),
            "center_low_height_bits": int(low.sum()),
            "center_low_speed_high_bits": int((slow & ~low).sum()),
            "center_high_speed_low_bits": int((~slow & low).sum()),
            "center_high_speed_high_bits": int((~slow & ~low).sum()),
            "center_low_speed_high_by_role": ";".join(
                f"{role}:{int((slow & ~low)[:, i].sum())}"
                for i, role in enumerate(FOOT_ROLES)),
            "center_foot_height_median_by_role_m": ";".join(
                f"{role}:{float(np.median(height[sl, i])):.4f}"
                for i, role in enumerate(FOOT_ROLES)),
            "center_local_floor_proxy_pairs": count_pairs(slow & local),
            "center_speed_030_absolute_floor_pairs": count_pairs(loose_speed & low),
            "center_speed_030_local_floor_pairs": count_pairs(loose_speed & local),
            "center_foot_height_p05_m": round(float(np.quantile(height[sl], .05)), 4),
            "center_foot_speed_p10_mps": round(float(np.quantile(velocity[sl], .10)), 4),
            "full_foot_floor_p05_min_m": round(float(floor.min()), 4),
            "full_foot_floor_p05_max_m": round(float(floor.max()), 4),
        }
        rows.append(row)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "review_metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_category = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    summary = {"contract_sha256": sha256(contract_path), "candidate_count": len(rows),
               "categories": {}, "interpretation_boundary":
               "Alternative foot speed and floor thresholds are diagnostic sensitivity probes, not physical contact truth."}
    fields = ("stored_center_pairs", "full_clip_stored_pairs", "center_contact_bits",
              "center_low_speed_bits", "center_low_height_bits", "center_low_speed_high_bits",
              "center_high_speed_low_bits", "center_high_speed_high_bits",
              "center_local_floor_proxy_pairs", "center_speed_030_absolute_floor_pairs",
              "center_speed_030_local_floor_pairs")
    for category, group in by_category.items():
        summary["categories"][category] = {"clips": len(group),
            "center_windows_without_stored_pairs": sum(row["stored_center_pairs"] == 0 for row in group),
            "center_windows_without_full_clip_pairs": sum(row["full_clip_stored_pairs"] == 0 for row in group),
            **{name: sum(row[name] for row in group) for name in fields}}
    summary["all"] = {"clips": len(rows), **{name: sum(row[name] for row in rows) for name in fields}}
    (output / "review_metrics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inspect(args.release, args.baseline, args.queue, args.output)
