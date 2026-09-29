"""Audit conservative toe-witness contact candidates without changing frozen labels.

The added foot-bone target means "low velocity while the same-side toe has an
existing contact bit". It is a training hypothesis, not physical contact truth.
"""

import argparse
import base64
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.conditioned_motion import load_raw
from motionbricks.data.unreal_dataset import contained_file


ROLES = ("left_foot", "left_toe", "right_foot", "right_toe")
EXAMPLES = (857, 201, 1587)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unpack(bits, frames):
    return np.unpackbits(np.frombuffer(base64.b64decode(bits, validate=True),
                                       dtype=np.uint8))[:frames * 4].reshape(frames, 4).astype(bool)


def world_feet(positions, root, feet):
    rotation = Rotation.from_quat(root[:, 3:]).as_matrix()
    return np.einsum("tij,tkj->tki", rotation, positions[:, feet]) + root[:, None, :3]


def contact_candidates(positions, root, feet, stored, fps):
    """Return float contact weights and diagnostic geometry for four foot roles."""
    world = world_feet(positions, root, feet)
    height = world[:, :, 1]
    speed = np.linalg.norm(np.diff(world, axis=0), axis=-1) * fps
    speed = np.concatenate((speed, speed[-1:]), axis=0)
    expected = (speed < .15) & (height < .10)
    if not np.array_equal(expected, stored):
        raise ValueError("Stored labels do not match the frozen contact heuristic")
    local_floor = np.quantile(height, .05, axis=0)
    weight = stored.astype(np.float32)
    added = np.zeros_like(stored)
    for foot, toe in ((0, 1), (2, 3)):
        added[:, foot] = (stored[:, toe] & (speed[:, foot] < .15)
                          & (height[:, foot] < local_floor[foot] + .08)
                          & ~stored[:, foot])
        weight[added[:, foot], foot] = .5
    return weight, added, height, speed, local_floor


def adjacent_pairs(bits):
    return int(np.count_nonzero(bits[1:] & bits[:-1]))


def plot_example(index, row, height, speed, stored, added, floor, middle, end, output):
    frames = np.arange(middle, end)
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 5.5), sharex=True,
                             constrained_layout=True)
    colors = ("#0086b3", "#21b37f", "#e09524", "#ab4f99")
    for bone, role in enumerate(ROLES):
        axes[0].plot(frames, height[middle:end, bone] * 100, color=colors[bone],
                     label=role, linewidth=1.6)
        axes[1].plot(frames, speed[middle:end, bone], color=colors[bone], linewidth=1.6)
        selected = frames[stored[middle:end, bone]]
        if len(selected):
            axes[1].scatter(selected, np.zeros(len(selected)), marker="|",
                            color=colors[bone], s=80)
        extra = frames[added[middle:end, bone]]
        if len(extra):
            axes[1].scatter(extra, np.full(len(extra), .22), marker="^",
                            color=colors[bone], s=20)
    axes[0].axhline(10, color="#b74444", linestyle="--", label="absolute gate 10 cm")
    axes[1].axhline(.15, color="#b74444", linestyle="--", label="speed gate 0.15 m/s")
    axes[0].set_ylabel("World bone height (cm)")
    axes[1].set_ylabel("World bone speed (m/s)")
    axes[1].set_xlabel("Source frame")
    axes[0].set_title(f"{row['category']} clip {index} | center 24 frames | bars: stored, triangles: provisional")
    axes[0].legend(ncol=3, fontsize=8)
    axes[1].legend(fontsize=8)
    axes[0].grid(alpha=.2)
    axes[1].grid(alpha=.2)
    fig.savefig(output / f"contact_{index}.png", dpi=150)
    plt.close(fig)


def audit(release, baseline_csv, queue_csv, output):
    if output.exists():
        raise FileExistsError(output)
    contract_path = release / "contract" / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source = Path(contract["source_dataset"])
    for filename, expected in (("dataset.json", contract["source_manifest_sha256"]),
                               ("skeleton.json", contract["skeleton_sha256"])):
        if sha256(source / filename) != expected:
            raise ValueError(f"Source changed: {filename}")
    skeleton = json.loads((source / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in ROLES]
    with baseline_csv.open(newline="", encoding="utf-8-sig") as stream:
        centers = {int(row["clip_index"]): int(row["start"])
                   for row in csv.DictReader(stream) if row["model"] == "generated_contact10"}
    with queue_csv.open(newline="", encoding="utf-8-sig") as stream:
        review = {int(row["clip_index"]): row for row in csv.DictReader(stream)}
    if len(review) != 30:
        raise ValueError("Expected 30 diagnostic review candidates")
    output.mkdir(parents=True)
    totals = defaultdict(Counter)
    rows = []
    for index, clip in enumerate(contract["clips"]):
        if clip["split"] not in ("train", "validation") or clip["category"] not in ("Walk", "Run", "Crouch"):
            continue
        raw, _ = load_raw(contained_file(source, clip["raw_file"]), clip["source_frames"],
                          contract["bone_count"], contract["fps"], expected_sha256=clip["raw_sha256"])
        stored = unpack(clip["contact_bits"], clip["source_frames"])
        weight, added, height, speed, floor = contact_candidates(
            raw["positions"], raw["root_track"], feet, stored, contract["fps"])
        group = totals[(clip["split"], clip["category"])]
        group["clips"] += 1
        group["stored_bits"] += int(stored.sum())
        group["stored_pairs"] += adjacent_pairs(stored)
        group["provisional_added_bits"] += int(added.sum())
        group["provisional_weighted_pairs"] += float((weight[1:] * weight[:-1]).sum())
        for role, bone in zip(ROLES, range(4)):
            group[f"added_{role}"] += int(added[:, bone].sum())
        if index in review:
            if clip["split"] != "validation" or clip["asset"] != review[index]["asset"]:
                raise ValueError(f"Review candidate mismatch at {index}")
            start = centers[index]
            middle = start + contract["window"]["history_frames"]
            end = middle + contract["window"]["future_frames"]
            item = {"clip_index": index, "category": clip["category"], "asset": clip["asset"],
                    "center_start": middle, "center_end_exclusive": end,
                    "stored_center_pairs": adjacent_pairs(stored[middle:end]),
                    "added_center_left_foot_bits": int(added[middle:end, 0].sum()),
                    "added_center_right_foot_bits": int(added[middle:end, 2].sum()),
                    "candidate_weighted_center_pairs": round(float(
                        (weight[middle + 1:end] * weight[middle:end - 1]).sum()), 3),
                    "left_foot_height_p05_m": round(float(floor[0]), 4),
                    "right_foot_height_p05_m": round(float(floor[2]), 4)}
            rows.append(item)
            if index in EXAMPLES:
                plot_example(index, item, height, speed, stored, added, floor, middle, end, output)
        if group["clips"] % 200 == 0:
            print(f"audited {clip['split']} {clip['category']} {group['clips']}", flush=True)
    if len(rows) != 30:
        raise ValueError("Not all 30 candidates were re-read")
    with (output / "candidate_review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"schema_version": 1, "contract_sha256": sha256(contract_path),
               "candidate_count": len(rows), "splits": ["train", "validation"],
               "rule": "Original contacts remain 1.0; add foot weight 0.5 only when ipsilateral toe has an original contact, foot speed <0.15 m/s, foot height < clip foot p05+0.08 m.",
               "interpretation": "Provisional training targets only, not ground-truth physical contact.",
               "by_split_category": {f"{split}/{cat}": dict(counts) for (split, cat), counts in sorted(totals.items())}}
    (output / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.release, args.baseline, args.queue, args.output)
