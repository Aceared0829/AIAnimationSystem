"""Join matched validation arms with audited Root-speed bins; keep test split untouched."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


ARMS = ("initial", "control3", "foot_velocity3")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def maybe_float(value):
    return None if value in (None, "") else float(value)


def average(rows, name):
    numbers = [maybe_float(row[name]) for row in rows]
    numbers = [value for value in numbers if value is not None and np.isfinite(value)]
    return float(np.mean(numbers)) if numbers else None


def aggregate(rows, fields):
    return {"clips": len(rows), "clips_with_contact_score": sum(row["contact_foot_speed_mps"] is not None for row in rows),
            **{field: average(rows, field) for field in fields}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed-map", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    speed_rows = read_csv(args.speed_map)
    speed = {int(row["clip_index"]): row for row in speed_rows}
    center_path = args.evaluation / "center_validation.csv"
    rollout_path = args.evaluation / "rollouts.csv"
    center = read_csv(center_path)
    rollout = read_csv(rollout_path)
    if len(speed) != 142 or len(center) != 142 * 3 or len(rollout) != 12 * 3:
        raise ValueError("matched frozen validation row count differs")
    for row in center:
        match = speed[int(row["clip_index"])]
        if row["category"] != match["category"]:
            raise ValueError("speed bin/center evaluation mismatch")
        row["speed_bin_mps"] = match["speed_bin"]
        row["contact_foot_speed_mps"] = maybe_float(row["contact_foot_speed_mps"])
        row["non_anchor_pose_rmse_cm"] = float(row["non_anchor_pose_rmse_cm"])
    for row in rollout:
        row["contact_foot_speed_mps"] = maybe_float(row["contact_foot_speed_mps"])
        row["chunk3_pose_rmse_cm"] = float(row["chunk3_pose_rmse_cm"])
    grouped = defaultdict(list)
    for row in center:
        grouped[(row["category"], row["speed_bin_mps"], row["model"])].append(row)
    categories = ("Walk", "Run", "Crouch")
    bins = ("0-0.2", "0.2-1", "1-2", "2-4", "4+")
    speed_table = [{"category": category, "speed_bin_mps": speed_bin, "model": model,
                    **aggregate(grouped[(category, speed_bin, model)],
                                ("non_anchor_pose_rmse_cm", "contact_foot_speed_mps"))}
                   for category in categories for speed_bin in bins for model in ARMS
                   if grouped[(category, speed_bin, model)]]
    category_table = [{"category": category, "model": model,
                       **aggregate([row for row in center if row["category"] == category and row["model"] == model],
                                   ("non_anchor_pose_rmse_cm", "contact_foot_speed_mps"))}
                      for category in categories for model in ARMS]
    rollout_table = [{"category": category, "model": model,
                      **aggregate([row for row in rollout if row["category"] == category and row["model"] == model],
                                  ("chunk3_pose_rmse_cm", "contact_foot_speed_mps"))}
                     for category in categories for model in ARMS]
    result = {"schema_version": 1, "split": "validation", "speed_map_sha256": sha256(args.speed_map),
              "center_csv_sha256": sha256(center_path), "rollout_csv_sha256": sha256(rollout_path),
              "arms": list(ARMS), "speed_table": speed_table, "category_table": category_table,
              "rollout_table": rollout_table,
              "limitations": ["Scores use source future Root; this is not a live CMC speed test.",
                              "Run 4+ m/s center scores rely on eight source contact pairs across seven clips.",
                              "Long rollouts include only four fixed validation clips per category."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"category_table": category_table, "rollout_table": rollout_table}, indent=2), flush=True)


if __name__ == "__main__":
    main()
