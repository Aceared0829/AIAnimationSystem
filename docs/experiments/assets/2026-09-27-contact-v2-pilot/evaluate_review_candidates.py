"""Score the 30 frozen review centers with original and provisional contact weights."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from contact_v2_audit import ROLES, contact_candidates, unpack
from data.runtime.conditioned_motion import load_raw, load_window
from inference.runtime.conditioned_pose import ConditionedPosePredictor
from motionbricks.data.unreal_dataset import apply_authoritative_root, contained_file
from training.pretrain.train_conditioned_pose import verify_release


ROOT = Path(__file__).resolve().parents[4]
RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def no_reference(values):
    result = dict(values)
    result["reference_pose"] = np.zeros_like(values["reference_pose"])
    result["reference_rotations"] = np.zeros_like(values["reference_rotations"])
    result["reference_frame_mask"] = np.zeros_like(values["reference_frame_mask"])
    result["reference_bone_mask"] = np.zeros_like(values["reference_bone_mask"])
    return result


def weighted_speed(pose, root, feet, weights, fps):
    world = apply_authoritative_root(pose, root)[:, feet]
    speed = np.linalg.norm(np.diff(world, axis=0), axis=-1) * fps
    pairs = weights[1:] * weights[:-1]
    return (float((speed * pairs).sum() / pairs.sum()) if pairs.sum() > 0 else None,
            float(pairs.sum()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--checkpoint", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    contract, _ = verify_release(RELEASE, LOCK)
    source = Path(contract["source_dataset"])
    skeleton = json.loads((source / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in ROLES]
    with args.baseline.open(newline="", encoding="utf-8-sig") as stream:
        centers = {int(row["clip_index"]): row for row in csv.DictReader(stream)
                   if row["model"] == "generated_contact10"}
    with args.queue.open(newline="", encoding="utf-8-sig") as stream:
        queue = {int(row["clip_index"]): row for row in csv.DictReader(stream)}
    if len(queue) != 30:
        raise ValueError("Expected 30 review candidates")
    paths = {}
    for item in args.checkpoint:
        name, equals, path = item.partition("=")
        if not equals or not name or name in paths:
            raise ValueError("Unique NAME=PATH checkpoint arguments required")
        paths[name] = Path(path)
    predictors = {name: ConditionedPosePredictor(path, RELEASE, LOCK) for name, path in paths.items()}
    rows = []
    for index, queue_row in queue.items():
        clip = contract["clips"][index]
        raw, _ = load_raw(contained_file(source, clip["raw_file"]), clip["source_frames"],
                          contract["bone_count"], contract["fps"], expected_sha256=clip["raw_sha256"])
        stored = unpack(clip["contact_bits"], clip["source_frames"])
        weights, _, _, _, _ = contact_candidates(raw["positions"], raw["root_track"], feet,
                                                  stored, contract["fps"])
        start = int(centers[index]["start"])
        middle = start + 24
        end = middle + 24
        sample = load_window(RELEASE / "contract", {"clip_index": index, "start": start}, contract=contract)
        input_values = no_reference(sample["input"])
        root = sample["target"]["future_root_track"]
        original = stored[middle:end].astype(np.float32)
        provisional = weights[middle:end]
        if queue_row["asset"] != clip["asset"]:
            raise ValueError(f"Review asset mismatch at {index}")
        for model_name, predictor in predictors.items():
            pose = predictor.predict(input_values)["future_pose"]
            old_speed, old_pairs = weighted_speed(pose, root, feet, original, contract["fps"])
            new_speed, new_pairs = weighted_speed(pose, root, feet, provisional, contract["fps"])
            rows.append({"clip_index": index, "category": clip["category"], "model": model_name,
                         "pose_rmse_cm": float(np.sqrt(np.mean((pose - sample["target"]["future_pose"]) ** 2)) * 100),
                         "stored_contact_speed_mps": old_speed,
                         "stored_contact_pairs": old_pairs,
                         "provisional_weighted_speed_mps": new_speed,
                         "provisional_weighted_pairs": new_pairs})
    args.output.mkdir(parents=True)
    with (args.output / "review_center_scores.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["category"], row["model"])].append(row)
    summary = {"schema_version": 1, "contract_sha256": sha256(RELEASE / "contract/contract.json"),
               "candidate_count": len(queue), "checkpoint_sha256": {name: sha256(path) for name, path in paths.items()},
               "score_note": "Per-clip mean then equal clip-weight mean; provisional contact weights are a hypothesis, not ground truth.",
               "by_category_model": {f"{category}/{model}": {
                   "clips": len(group), "clips_with_stored_pairs": sum(row["stored_contact_pairs"] > 0 for row in group),
                   "stored_pairs": sum(row["stored_contact_pairs"] for row in group),
                   "provisional_weighted_pairs": sum(row["provisional_weighted_pairs"] for row in group),
                   "stored_contact_speed_clip_mean_mps": float(np.mean([
                       row["stored_contact_speed_mps"] for row in group if row["stored_contact_speed_mps"] is not None])),
                   "provisional_speed_clip_mean_mps": float(np.mean([
                       row["provisional_weighted_speed_mps"] for row in group
                       if row["provisional_weighted_speed_mps"] is not None])),
                   "pose_rmse_clip_mean_cm": float(np.mean([row["pose_rmse_cm"] for row in group]))}
                   for (category, model), group in sorted(grouped.items())}}
    (args.output / "review_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
