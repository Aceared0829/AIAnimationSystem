"""Per-clip validation of pose, rotation, motion continuity, and heuristic foot contact."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from data.runtime.conditioned_motion import load_window, with_references
from inference.runtime.conditioned_pose import ConditionedPosePredictor
from training.evaluation.evaluate_conditioned_baselines import aggregate, score, select_windows


SCENARIOS = {"no_refs": (), "one_middle": (12,), "one_end": (23,),
             "two_refs": (12, 23), "off_grid": (5, 18)}


def evaluate(checkpoint, release, lock, output, *, split="validation", source_override=None):
    if split not in ("validation", "test"):
        raise ValueError("Only frozen validation or test splits are accepted")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    predictor = ConditionedPosePredictor(checkpoint, release, lock, source_override)
    contract = predictor.contract
    source = Path(contract["source_dataset"])
    skeleton = json.loads((source / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in
            ("left_foot", "left_toe", "right_foot", "right_toe")]
    rows = select_windows(Path(release) / "contract" / "windows.jsonl", contract, split, 1)
    grouped = defaultdict(list)
    by_category = defaultdict(list)
    for row in rows:
        base = load_window(Path(release) / "contract", row, contract=contract)
        for scenario, offsets in SCENARIOS.items():
            sample = with_references(base, offsets)
            prediction = predictor.predict(sample["input"])
            result = score(sample, prediction["future_pose"], prediction["future_rotations"],
                           feet, contract["fps"])
            result["clip_index"] = row["clip_index"]
            grouped[scenario].append(result)
            by_category[f"{sample['metadata']['category']}/{scenario}"].append(result)
    report = {"checkpoint": str(Path(checkpoint).resolve()),
              "contract_sha256": predictor.config["contract_sha256"],
              "split": split, "selection": "middle_window_per_clip", "clips": len(rows),
              "oracle_root_condition": True,
              "contact_label_source": "heuristic_from_ground_truth_pose_and_root",
              "scenarios": {key: aggregate(value) for key, value in sorted(grouped.items())},
              "by_category": {key: aggregate(value) for key, value in sorted(by_category.items())},
              "limitations": ["Root path is the original motion, not a controller prediction.",
                              "Contact labels are heuristic; UE visual acceptance remains necessary."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--lock", required=True)
    parser.add_argument("--source-override")
    parser.add_argument("--output", required=True)
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    args = parser.parse_args()
    result = evaluate(args.checkpoint, args.release, args.lock, args.output,
                      split=args.split, source_override=args.source_override)
    print(json.dumps({"output": str(Path(args.output).resolve()), "clips": result["clips"],
                      "scenarios": result["scenarios"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
