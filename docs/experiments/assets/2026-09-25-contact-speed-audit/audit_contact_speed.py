"""Audit frozen locomotion contact labels and group existing validation scores by Root speed.

This is a read-only diagnostic. A local-floor label is an alternative geometric
proxy, not ground truth, and must never be written back into the frozen release.
"""

import argparse
import base64
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.conditioned_motion import load_raw
from motionbricks.data.unreal_dataset import UnrealSkeleton, contained_file, world_foot_contacts


CATEGORIES = ("Walk", "Run", "Crouch")
FOOT_ROLES = ("left_foot", "left_toe", "right_foot", "right_toe")
SPEED_BINS = (("0-0.2", 0.2), ("0.2-1", 1.0), ("1-2", 2.0),
              ("2-4", 4.0), ("4+", float("inf")))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unpack_contacts(clip):
    packed = np.frombuffer(base64.b64decode(clip["contact_bits"], validate=True), dtype=np.uint8)
    return np.unpackbits(packed)[:clip["source_frames"] * 4].reshape(-1, 4).astype(bool)


def world_feet(raw, feet):
    rotation = Rotation.from_quat(raw["root_track"][:, 3:]).as_matrix()
    return np.einsum("tij,tkj->tki", rotation, raw["positions"][:, feet]) + raw["root_track"][:, None, :3]


def runs_by_foot(contacts):
    lengths = []
    for foot in range(4):
        frames = np.flatnonzero(contacts[:, foot])
        if len(frames):
            lengths.extend(len(run) for run in np.split(frames, np.flatnonzero(np.diff(frames) != 1) + 1))
    return lengths


def speed_bin(speed):
    return next(name for name, upper in SPEED_BINS if speed < upper)


def maybe_float(value):
    return None if value in (None, "") else float(value)


def mean(values):
    return float(np.mean(values)) if values else None


def aggregate(rows):
    with_pairs = [row for row in rows if row["contact_pairs"]]
    pairs = sum(row["contact_pairs"] for row in with_pairs)
    return {
        "clips": len(rows),
        "clips_with_contact_pairs": len(with_pairs),
        "clips_without_contact_pairs": len(rows) - len(with_pairs),
        "contact_pairs": pairs,
        "root_speed_mean_mps": mean([row["root_speed_mean_mps"] for row in rows]),
        "pose_rmse_clip_mean_cm": mean([row["pose_rmse_cm"] for row in rows]),
        "source_contact_speed_clip_mean_mps": mean([row["source_contact_speed_mps"] for row in with_pairs]),
        "model_contact_speed_clip_mean_mps": mean([row["model_contact_speed_mps"] for row in with_pairs]),
        "source_contact_speed_pair_weighted_mps":
            sum(row["source_contact_speed_mps"] * row["contact_pairs"] for row in with_pairs) / pairs if pairs else None,
        "model_contact_speed_pair_weighted_mps":
            sum(row["model_contact_speed_mps"] * row["contact_pairs"] for row in with_pairs) / pairs if pairs else None,
    }


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit(release, baseline_csv, output, model):
    if output.exists():
        raise FileExistsError(output)
    contract_path = release / "contract" / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    source = Path(contract["source_dataset"])
    if sha256(source / "dataset.json") != contract["source_manifest_sha256"]:
        raise ValueError("source manifest differs from frozen contract")
    if sha256(source / "skeleton.json") != contract["skeleton_sha256"]:
        raise ValueError("source skeleton differs from frozen contract")
    skeleton_json = json.loads((source / "skeleton.json").read_text(encoding="utf-8"))
    manifest = json.loads((source / "dataset.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton_json["bones"]]
    feet = [names.index(skeleton_json["roles"][role]) for role in FOOT_ROLES]
    skeleton = UnrealSkeleton(source)
    fps = contract["fps"]

    with baseline_csv.open(newline="", encoding="utf-8-sig") as stream:
        existing = [row for row in csv.DictReader(stream) if row["model"] == model]
    if len(existing) != 142 or len({int(row["clip_index"]) for row in existing}) != len(existing):
        raise ValueError("expected 142 distinct frozen validation center windows")
    by_index = {int(row["clip_index"]): row for row in existing}

    clip_rows, score_rows = [], []
    label_totals = Counter()
    for index, clip in enumerate(contract["clips"]):
        if clip["category"] not in CATEGORIES:
            continue
        if clip["asset"] != manifest["clips"][index]["asset"] or clip["split"] != manifest["clips"][index]["split"]:
            raise ValueError(f"contract/source mismatch at clip {index}")
        raw, _ = load_raw(contained_file(source, clip["raw_file"]), clip["source_frames"],
                          contract["bone_count"], fps, expected_sha256=clip["raw_sha256"])
        stored = unpack_contacts(clip)
        derived = world_foot_contacts(raw["positions"], raw["root_track"], skeleton, fps).numpy() > 0.5
        if not np.array_equal(stored, derived):
            raise ValueError(f"stored/derived contact mismatch at clip {index}")
        world = world_feet(raw, feet)
        # The frozen heuristic uses forward differences and repeats the final speed.
        forward = np.linalg.norm(np.diff(world, axis=0), axis=-1) * fps
        forward = np.concatenate((forward, forward[-1:]), axis=0)
        absolute_height = world[:, :, 1] < 0.10
        local_floor = np.quantile(world[:, :, 1], 0.05, axis=0)
        local_proxy = (forward < 0.15) & (world[:, :, 1] < local_floor[None] + 0.10)
        pair = stored[1:] & stored[:-1]
        run_lengths = runs_by_foot(stored)
        joint_count = stored.size
        label_totals[(clip["category"], "frames")] += joint_count
        label_totals[(clip["category"], "labels")] += int(stored.sum())
        label_totals[(clip["category"], "pairs")] += int(pair.sum())
        label_totals[(clip["category"], "proxy_only")] += int((local_proxy & ~stored).sum())
        label_totals[(clip["category"], "stored_only")] += int((stored & ~local_proxy).sum())
        label_totals[(clip["category"], "height_only")] += int(absolute_height.sum())
        label_totals[(clip["category"], "runs")] += len(run_lengths)
        label_totals[(clip["category"], "one_frame_runs")] += sum(length == 1 for length in run_lengths)
        clip_rows.append({
            "clip_index": index, "split": clip["split"], "category": clip["category"],
            "phase": manifest["clips"][index]["labels"]["phase"], "asset": clip["asset"],
            "source_frames": clip["source_frames"], "stored_contact_fraction": round(float(stored.mean()), 6),
            "stored_contact_pairs": int(pair.sum()), "stored_contact_runs": len(run_lengths),
            "one_frame_contact_runs": sum(length == 1 for length in run_lengths),
            "local_floor_proxy_only_fraction": round(float((local_proxy & ~stored).mean()), 6),
            "stored_only_fraction": round(float((stored & ~local_proxy).mean()), 6),
            "world_foot_height_p05_m": round(float(np.quantile(world[:, :, 1], 0.05)), 4),
            "world_foot_height_p95_m": round(float(np.quantile(world[:, :, 1], 0.95)), 4),
        })
        if index in by_index:
            score = by_index[index]
            start = int(score["start"])
            middle = start + contract["window"]["history_frames"]
            end = middle + contract["window"]["future_frames"]
            future_speed = np.linalg.norm(np.diff(raw["root_track"][middle - 1:end, :3], axis=0)[:, [0, 2]], axis=-1) * fps
            center_pairs = int((stored[middle + 1:end] & stored[middle:end - 1]).sum())
            if center_pairs != int(score["contact_pairs"]):
                raise ValueError(f"baseline contact count differs at clip {index}")
            score_rows.append({
                "clip_index": index, "category": clip["category"], "phase": manifest["clips"][index]["labels"]["phase"],
                "asset": clip["asset"], "root_speed_mean_mps": float(future_speed.mean()),
                "root_speed_std_mps": float(future_speed.std()), "speed_bin": speed_bin(float(future_speed.mean())),
                "contact_pairs": center_pairs, "pose_rmse_cm": float(score["all_pose_rmse_cm"]),
                "source_contact_speed_mps": maybe_float(score["source_contact_foot_speed_mps"]),
                "model_contact_speed_mps": maybe_float(score["contact_foot_speed_mps"]),
                "local_floor_proxy_only_fraction": clip_rows[-1]["local_floor_proxy_only_fraction"],
            })
        if (index + 1) % 200 == 0:
            print(f"scanned manifest position {index + 1}/{len(contract['clips'])}", flush=True)

    if len(score_rows) != len(existing):
        raise ValueError("not every validation score matched a frozen clip")
    grouped = defaultdict(list)
    for row in score_rows:
        grouped[(row["category"], row["speed_bin"])].append(row)
    speed_table = [{"category": category, "speed_bin_mps": name, **aggregate(grouped[(category, name)])}
                   for category in CATEGORIES for name, _ in SPEED_BINS]
    phases = defaultdict(list)
    for row in score_rows:
        phases[(row["category"], row["phase"])].append(row)
    phase_table = [{"category": category, "phase": phase, **aggregate(rows)}
                   for (category, phase), rows in sorted(phases.items())]
    contact_table = []
    for category in CATEGORIES:
        rows = [row for row in clip_rows if row["category"] == category]
        count = label_totals[(category, "frames")]
        contact_table.append({
            "category": category, "clips": len(rows),
            "split_counts": dict(Counter(row["split"] for row in rows)),
            "zero_pair_clips": sum(row["stored_contact_pairs"] == 0 for row in rows),
            "label_fraction": label_totals[(category, "labels")] / count,
            "contact_pairs": label_totals[(category, "pairs")],
            "one_frame_run_fraction": label_totals[(category, "one_frame_runs")] / max(label_totals[(category, "runs")], 1),
            "local_floor_proxy_only_fraction": label_totals[(category, "proxy_only")] / count,
            "stored_only_fraction": label_totals[(category, "stored_only")] / count,
            "absolute_height_below_10cm_fraction": label_totals[(category, "height_only")] / count,
        })
    review = sorted(score_rows, key=lambda row: (row["contact_pairs"] > 3,
                    -(row["local_floor_proxy_only_fraction"]), -row["root_speed_mean_mps"]))[:30]
    report = {
        "schema_version": 1, "kind": "frozen_contact_and_speed_validation_diagnostic",
        "contract_sha256": sha256(contract_path), "source_manifest_sha256": sha256(source / "dataset.json"),
        "baseline_csv_sha256": sha256(baseline_csv), "baseline_model": model,
        "baseline_conditions": "validation center window, no future pose reference, source future Root, existing predicted score",
        "label_definition": "world foot speed <0.15 m/s AND absolute world foot height <0.10 m; forward difference",
        "alternative_proxy": "world foot speed <0.15 m/s AND height < per-clip per-foot p05 height +0.10 m; not physical truth",
        "contact": contact_table, "speed": speed_table, "phase": phase_table,
        "validation_all": aggregate(score_rows),
        "validation_by_category": {category: aggregate([row for row in score_rows if row["category"] == category])
                                   for category in CATEGORIES},
        "limitations": ["Stored-versus-recomputed equality checks the pipeline, not real floor contact.",
                        "The local-floor proxy is heuristic and may be wrong on steps, slopes, and airborne motion.",
                        "Model scores reuse a prior evaluation with oracle source future Root, not live CMC.",
                        "Speed bins on 142 center validation clips are descriptive, not a new test set."],
    }
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(output / "clips.csv", clip_rows, list(clip_rows[0]))
    write_csv(output / "validation_scores.csv", score_rows, list(score_rows[0]))
    write_csv(output / "review_queue.csv", review, list(score_rows[0]))
    print(json.dumps({"contact": contact_table, "validation_all": report["validation_all"]},
                     ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--baseline-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="generated_contact10")
    args = parser.parse_args()
    audit(args.release, args.baseline_csv, args.output, args.model)


if __name__ == "__main__":
    main()
