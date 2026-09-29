"""Summarize fixed validation centers and rollouts by category and Root-speed bin."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


MODELS = ("control", "toe_witness", "speed_phase")
FIELDS = ("non_anchor_pose_rmse_cm", "contact_foot_speed_mps",
          "predicted_jump_cm", "causal_root_rmse_cm")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def mean(rows, field):
    values = [float(row[field]) for row in rows if row.get(field) not in (None, "")]
    return float(np.mean(values)) if values else None


def summarize(rows, fields):
    return {"clips": len(rows), "contact_pairs": sum(int(row.get("contact_pairs", 0)) for row in rows),
            "clips_with_contact_score": sum(row.get("contact_foot_speed_mps") not in (None, "") for row in rows),
            **{field: mean(rows, field) for field in fields}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed-map", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    speed = {int(row["clip_index"]): row for row in read(args.speed_map)}
    center = read(args.evaluation / "center_validation.csv")
    rollout = read(args.evaluation / "rollouts.csv")
    replan = read(args.evaluation / "rollouts_4frame.csv")
    if len(speed) != 142 or len(center) != 142 * 3 or len(rollout) != 12 * 3 or len(replan) != 12 * 3:
        raise ValueError("Frozen validation row count differs")
    if {row["model"] for row in center} != set(MODELS):
        raise ValueError("Model arms differ")
    bins = defaultdict(list)
    categories = defaultdict(list)
    for row in center:
        match = speed[int(row["clip_index"])]
        if match["category"] != row["category"] or int(match["contact_pairs"]) != int(row["contact_pairs"]):
            raise ValueError("Speed/contact audit does not match current evaluation")
        bins[(row["category"], match["speed_bin"], row["model"])].append(row)
        categories[(row["category"], row["model"])].append(row)
    report = {"schema_version": 1, "split": "validation", "models": MODELS,
              "conditions": "No future pose reference; source future Root for pose score and long rollouts; causal Root sensitivity is reported separately.",
              "speed_map_sha256": sha256(args.speed_map),
              "center_sha256": sha256(args.evaluation / "center_validation.csv"),
              "rollout_sha256": sha256(args.evaluation / "rollouts.csv"),
              "replan_sha256": sha256(args.evaluation / "rollouts_4frame.csv"),
              "category": {f"{cat}/{model}": summarize(rows, FIELDS)
                           for (cat, model), rows in sorted(categories.items())},
              "speed_bin": {f"{cat}/{speed_bin}/{model}": summarize(rows, FIELDS)
                            for (cat, speed_bin, model), rows in sorted(bins.items())},
              "rollout": {f"{cat}/{model}": summarize(
                  [row for row in rollout if row["category"] == cat and row["model"] == model],
                  ("chunk3_pose_rmse_cm", "contact_foot_speed_mps", "replan_seam_jump_cm"))
                          for cat in ("Walk", "Run", "Crouch") for model in MODELS},
              "four_frame_replan": {f"{cat}/{model}": summarize(
                  [row for row in replan if row["category"] == cat and row["model"] == model],
                  ("block3_pose_rmse_cm", "contact_foot_speed_mps", "replan_seam_jump_cm"))
                  for cat in ("Walk", "Run", "Crouch") for model in MODELS},
              "limitations": ["Stored contact bits are heuristic and favor low source foot speed.",
                              "Run >=4 m/s has only eight contact pairs across seven validation clips.",
                              "Only four long rollout clips per category; this is not live player input or UE physics."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"category": report["category"], "four_frame_replan": report["four_frame_replan"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
