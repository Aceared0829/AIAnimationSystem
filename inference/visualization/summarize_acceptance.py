"""Combine same-trajectory, controller, and decoder-ablation evidence."""

import argparse
import json
from pathlib import Path

import numpy as np


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def by_category(report):
    return {entry["category"]: entry for entry in report["clips"]}


def ablation(default_dir, oracle_dir):
    default = read(Path(default_dir) / "report.json")
    oracle = read(Path(oracle_dir) / "report.json")
    if (default["pose_checkpoint_sha256"] != oracle["pose_checkpoint_sha256"]
            or default["dataset_manifest_sha256"] != oracle["dataset_manifest_sha256"]
            or default["skeleton_sha256"] != oracle["skeleton_sha256"]
            or default.get("decoder_pose_root_oracle")
            or not oracle.get("decoder_pose_root_oracle")
            or default["input_visibility"]["future_source_pose_feature_root_frames"] != 0):
        raise ValueError("Decoder ablation reports do not share a causal default/model/data")
    result = {}
    for category, entry in by_category(default).items():
        counterpart = by_category(oracle)[category]
        if (entry["clip_index"] != counterpart["clip_index"]
                or entry["source_frame_start"] != counterpart["source_frame_start"]):
            raise ValueError("Decoder ablation clip selection differs")
        with np.load(Path(default_dir) / entry["arrays"], allow_pickle=False) as base, \
                np.load(Path(oracle_dir) / counterpart["arrays"], allow_pickle=False) as leaked:
            if (not np.array_equal(base["tokens"], leaked["tokens"])
                    or not np.array_equal(base["source"], leaked["source"])
                    or not np.array_equal(base["actor_root"], leaked["actor_root"])):
                raise ValueError("Decoder ablation changed tokens, source, or Actor Root")
        names = ("joint_rmse_cm", "generated_contact_foot_speed_mps",
                 "foot_velocity_rmse_mps")
        result[category] = {
            "clip_index": entry["clip_index"],
            "source_contact_pairs": entry["metrics"]["source_contact_pairs"],
            "pose_tokens_exactly_equal": True,
            "metrics": {
                name: {
                    "zero_external": entry["metrics"].get(name),
                    "future_true_pose_root_oracle": counterpart["metrics"].get(name),
                } for name in names
            },
        }
    return result


def selected_metrics(comparison):
    return {
        entry["category"]: {
            "clip_index": entry["clip_index"],
            "source_contact_pairs": entry["source_contact_pairs"],
            "source_contact_foot_speed_mps": entry.get("source_contact_foot_speed_mps"),
            "joint_rmse_cm": entry["metrics"]["joint_rmse_cm"],
            "contact_foot_speed_mps": entry["metrics"]["generated_contact_foot_speed_mps"],
            "foot_velocity_rmse_mps": entry["metrics"]["foot_velocity_rmse_mps"],
            "seam_velocity_error_cm_per_frame": entry["metrics"]["seam_velocity_error_cm_per_frame"],
            "body_facing_rmse_vs_source_deg": entry["metrics"]["body_facing_rmse_vs_source_deg"],
            "representative_frame_png": entry.get("representative_frame_png"),
            "comparison_video": entry.get("video"),
        } for entry in comparison["clips"]
    }


def summarize(args):
    default = read(args.comparison_default)
    contact = read(args.comparison_contacts)
    teacher = read(Path(args.teacher) / "report.json")
    cmc = read(Path(args.cmc) / "report.json")
    if (default["motionweaver_checkpoint_sha256"] != contact["motionweaver_checkpoint_sha256"]
            or default["motionweaver_checkpoint_sha256"] != teacher["pose_checkpoint_sha256"]
            or default["motionweaver_checkpoint_sha256"] != cmc["pose_checkpoint_sha256"]):
        raise ValueError("Acceptance inputs do not use the same MotionWeaver checkpoint")
    if (teacher["dataset_manifest_sha256"] != cmc["dataset_manifest_sha256"]
            or teacher["skeleton_sha256"] != cmc["skeleton_sha256"]):
        raise ValueError("Teacher and CMC probes have different prepared data")
    if (teacher["input_visibility"]["future_source_pose_frames"] != 0
            or teacher["input_visibility"]["future_source_pose_feature_root_frames"] != 0
            or cmc["input_visibility"]["future_source_pose_frames"] != 0
            or cmc["input_visibility"]["future_source_pose_feature_root_frames"] != 0
            or cmc["input_visibility"]["future_source_actor_root_frames"] != 0):
        raise ValueError("Causal probes contain future source pose or Root")
    result = {
        "schema_version": 1,
        "checkpoint_sha256": teacher["pose_checkpoint_sha256"],
        "checkpoint_training_steps": teacher["pose_checkpoint_training_steps"],
        "run_label": teacher.get("run_label", ""),
        "device": teacher["forward_timing"]["device_name"],
        "input_contract": {
            "historical_source_pose_frames": 4,
            "future_source_pose_frames": 0,
            "teacher_future_root": teacher["actor_root_source"],
            "controller_future_root": cmc["future_root_source"],
            "cmc_crouch_state_supplied_to_model": False,
        },
        "same_trajectory_loops": selected_metrics(default),
        "same_trajectory_contact_stops": selected_metrics(contact),
        "recorded_cmc_controller": {
            entry["category"]: {
                "clip_index": entry["clip_index"],
                "controller_metrics": entry["controller_metrics"],
                "video": entry.get("video"),
                "representative_frame_png": entry.get("poster"),
            } for entry in cmc["clips"]
        },
        "decoder_pose_root_oracle_ablation": ablation(args.teacher, args.oracle),
        "forward_timing_teacher": teacher["forward_timing"],
        "forward_timing_cmc": cmc["forward_timing"],
        "limits": [
            "Old model has 24 history poses; MotionWeaver has four",
            "Teacher trajectory is an exported Actor Root offline oracle, not live CMC",
            "CMC source-panel pose is counterfactual, not controller ground truth",
            "World turn from Actor transform is not proof that local model pose responds to turn",
            "Crouch CMC flag is omitted from model inputs",
            "Contact speed requires consecutive source-contact pairs and is not calibrated on changed CMC paths",
            "Timing excludes all UE runtime work and Python preprocessing",
        ],
    }
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-default", type=Path, required=True)
    parser.add_argument("--comparison-contacts", type=Path, required=True)
    parser.add_argument("--teacher", type=Path, required=True)
    parser.add_argument("--cmc", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(summarize(parser.parse_args()), ensure_ascii=False, indent=2))
