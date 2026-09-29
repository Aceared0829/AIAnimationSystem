"""Summarize matched Root/pose sliding from UE world-bone readback."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


LANES = ("source_source", "source_cmc", "model_plan", "model_cmc")
FEET = ("foot_l", "ball_l", "foot_r", "ball_r")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_bones(path):
    values = {}
    errors = []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            key = (row["scenario"], row["lane"])
            if key not in values:
                values[key] = np.full((72, 4, 3), np.nan, dtype=np.float64)
            values[key][int(row["frame"]), FEET.index(row["bone"])] = [float(row[f"world_{axis}_cm"]) for axis in "xyz"]
            errors.append(float(row["error_cm"]))
    if len(errors) != 3 * 4 * 72 * 4 or any(not np.isfinite(item).all() for item in values.values()):
        raise ValueError("missing UE bone readback rows")
    return values, errors


def contact_metrics(world_cm, contacts):
    paired = contacts[1:] & contacts[:-1]
    speed = np.linalg.norm(np.diff(world_cm, axis=0), axis=-1) * 0.3
    drifts = []
    for foot in range(4):
        frames = np.flatnonzero(contacts[:, foot])
        if not len(frames):
            continue
        runs = np.split(frames, np.flatnonzero(np.diff(frames) != 1) + 1)
        for run in runs:
            if len(run) >= 2:
                drifts.append(float(np.linalg.norm(world_cm[run, foot] - world_cm[run[0], foot], axis=1).max()))
    return {"source_contact_pairs": int(paired.sum()),
            "contact_foot_speed_mean_mps": float(speed[paired].mean()) if paired.any() else None,
            "contact_run_max_drift_mean_cm": float(np.mean(drifts)) if drifts else None,
            "contact_run_max_drift_max_cm": float(np.max(drifts)) if drifts else None,
            "contact_runs": len(drifts),
            "foot_boundary_step_mean_cm": [float(np.linalg.norm(world_cm[frame] - world_cm[frame - 1], axis=-1).mean())
                                           for frame in (24, 48)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--ue-render", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = json.loads((args.fixtures / "manifest.json").read_text(encoding="utf-8"))
    bones, errors = load_bones(args.ue_render / "bone_readback.csv")
    report = {"schema_version": 1, "fixture_manifest_sha256": sha256(args.fixtures / "manifest.json"),
              "ue_bone_readback_sha256": sha256(args.ue_render / "bone_readback.csv"),
              "ue_world_bone_error_max_cm": float(max(errors)),
              "contact_label_source": "frozen source-pose heuristic, not physical CMC ground truth",
              "fps": 30, "cases": []}
    for case in manifest["cases"]:
        scenario = case["scenario"]
        contacts = np.fromfile(args.fixtures / scenario / "source_contacts.f32", dtype="<f4").reshape(72, 4) > 0.5
        result = {"scenario": scenario, "clip_index": case["clip_index"], "split": case["split"],
                  "source_speed_mps": case["source_speed_mps"], "cmc_speed_mps": case["cmc_speed_mps"],
                  "source_cmc_velocity_gap_mps": case["source_cmc_velocity_gap_mps"],
                  "root_plan_error_mean_cm": case["root_plan_error_mean_cm"],
                  "root_plan_error_max_cm": case["root_plan_error_max_cm"], "lanes": {}}
        for lane in LANES:
            result["lanes"][lane] = contact_metrics(bones[(scenario, lane)], contacts)
        report["cases"].append(result)
        print(f"{scenario}: " + ", ".join(f"{lane}={result['lanes'][lane]['contact_foot_speed_mean_mps']:.3f} m/s"
                                         for lane in LANES), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
