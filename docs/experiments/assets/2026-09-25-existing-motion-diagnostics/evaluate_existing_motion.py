"""Read-only no-reference diagnostics for frozen conditioned pose checkpoints."""

import argparse
import csv
import hashlib
import json
import math
import platform
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import scipy
import torch
from scipy.spatial.transform import Rotation

from data.runtime.conditioned_motion import load_raw, load_window, root_local
from inference.runtime.conditioned_pose import ConditionedPosePredictor
from motionbricks.data.unreal_dataset import apply_authoritative_root
from training.evaluation.evaluate_conditioned_baselines import score, select_windows


ROOT = Path(__file__).resolve().parents[4]
RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
CHECKPOINTS = {
    "uniform12": Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_uniform12\epoch_012.pt"),
    "hybrid12": Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_hybrid12\epoch_012.pt"),
}
CORE = {"Walk", "Run", "Crouch"}
ROLLOUTS = {
    "Walk": (1306, 1420, 1486, 1675),
    "Run": (983, 836, 913, 1077),
    "Crouch": (49, 154, 201, 376),
}


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mean_or_none(values):
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return float(np.mean(clean)) if clean else None


def root_plan_from_history(history, future_frames=24, velocity_frames=6):
    """Straight constant-velocity/yaw extrapolation using past Root only."""
    if len(history) < velocity_frames + 1:
        raise ValueError("Not enough Root history")
    recent = history[-(velocity_frames + 1):]
    step_world = np.diff(recent[:, :3], axis=0).mean(axis=0)
    rotations = Rotation.from_quat(recent[:, 3:])
    local_steps = (rotations[:-1].inv() * rotations[1:]).as_rotvec()
    yaw_step = float(np.mean(local_steps[:, 1]))
    last = history[-1]
    origin_rotation = Rotation.from_quat(last[3:])
    out = np.zeros((future_frames, 7), dtype=np.float32)
    for frame in range(future_frames):
        count = frame + 1
        out[frame, :3] = last[:3] + step_world * count
        out[frame, 3:] = (origin_rotation * Rotation.from_rotvec([0, yaw_step * count, 0])).as_quat()
    return out


def no_reference(visible):
    result = dict(visible)
    result["reference_pose"] = np.zeros_like(visible["reference_pose"])
    result["reference_rotations"] = np.zeros_like(visible["reference_rotations"])
    result["reference_frame_mask"] = np.zeros_like(visible["reference_frame_mask"])
    result["reference_bone_mask"] = np.zeros_like(visible["reference_bone_mask"])
    return result


def world_pose(pose, root):
    return apply_authoritative_root(np.asarray(pose), np.asarray(root))


def seam_metrics(history_pose, history_root, predicted_pose, predicted_root, source_pose, source_root):
    history_world = world_pose(history_pose[-2:], history_root[-2:])
    predicted_world = world_pose(predicted_pose[:1], predicted_root[:1])[0]
    source_world = world_pose(source_pose[:1], source_root[:1])[0]
    last = history_world[-1]
    return {
        "predicted_jump_cm": float(np.linalg.norm(predicted_world - last, axis=-1).mean() * 100),
        "source_jump_cm": float(np.linalg.norm(source_world - last, axis=-1).mean() * 100),
        "first_frame_error_cm": float(np.linalg.norm(predicted_world - source_world, axis=-1).mean() * 100),
        "predicted_velocity_change_cm_per_frame": float(np.linalg.norm(
            (predicted_world - last) - (history_world[-1] - history_world[-2]), axis=-1).mean() * 100),
    }


def contact_speed(pose, root, contacts, feet, fps):
    world = world_pose(pose, root)
    speeds = np.linalg.norm(np.diff(world[:, feet], axis=0), axis=-1) * fps
    paired = contacts[1:] & contacts[:-1]
    return (float(speeds[paired].mean()) if paired.any() else None, int(paired.sum()))


def aggregate(rows, fields):
    return {field: mean_or_none(row[field] for row in rows) for field in fields} | {"clips": len(rows)}


def run_center_windows(predictors, contract, manifest, feet):
    rows = select_windows(RELEASE / "contract/windows.jsonl", contract, "validation", 1)
    rows = [row for row in rows if contract["clips"][row["clip_index"]]["category"] in CORE]
    results = []
    for number, row in enumerate(rows, 1):
        sample = load_window(RELEASE / "contract", row, contract=contract)
        labels = manifest["clips"][row["clip_index"]]["labels"]
        visible = no_reference(sample["input"])
        true_root = sample["target"]["future_root_track"]
        source = sample["target"]["future_pose"]
        history_root = load_history_root(contract, row)
        causal_root = root_plan_from_history(history_root)
        origin = history_root[-1]
        causal_visible = dict(visible, future_root_plan_local=root_local(causal_root, origin))
        root_rmse = float(np.sqrt(np.mean(np.sum((causal_root[:, :3] - true_root[:, :3]) ** 2, axis=-1))) * 100)
        root_end = float(np.linalg.norm(causal_root[-1, :3] - true_root[-1, :3]) * 100)
        for model_name, predictor in predictors.items():
            predicted = predictor.predict(visible)
            causal = predictor.predict(causal_visible)
            quality = score(sample, predicted["future_pose"], predicted["future_rotations"], feet, contract["fps"])
            seam = seam_metrics(visible["history_pose"], history_root, predicted["future_pose"], true_root,
                                source, true_root)
            change = float(np.sqrt(np.mean(np.sum((causal["future_pose"] - predicted["future_pose"]) ** 2,
                                                 axis=-1))) * 100)
            results.append({"clip_index": row["clip_index"], "asset": sample["metadata"]["asset"],
                            "category": sample["metadata"]["category"], "start": row["start"],
                            "phase": labels["phase"], "style": labels["style"], "direction": labels["direction"],
                            "model": model_name, "causal_root_rmse_cm": root_rmse,
                            "causal_root_end_error_cm": root_end, "pose_change_under_causal_root_cm": change,
                            **quality, **seam})
        if number % 25 == 0 or number == len(rows):
            print(f"center validation {number}/{len(rows)}", flush=True)
    return results


def load_history_root(contract, row):
    clip = contract["clips"][row["clip_index"]]
    path = Path(contract["source_dataset"]) / clip["raw_file"]
    raw, _ = load_raw(path, clip["source_frames"], contract["bone_count"], contract["fps"],
                      expected_sha256=clip["raw_sha256"])
    start = row["start"]
    return raw["root_track"][start:start + 24]


def run_rollouts(predictors, contract, manifest, feet):
    results = []
    source = Path(contract["source_dataset"])
    fps = contract["fps"]
    for category, indices in ROLLOUTS.items():
        for index in indices:
            clip = contract["clips"][index]
            labels = manifest["clips"][index]["labels"]
            if clip["split"] != "validation" or clip["category"] != category or clip["source_frames"] < 96:
                raise ValueError(f"Invalid fixed rollout clip {index}")
            raw, _ = load_raw(source / clip["raw_file"], clip["source_frames"], contract["bone_count"], fps,
                              expected_sha256=clip["raw_sha256"])
            bits = np.unpackbits(np.frombuffer(__import__("base64").b64decode(clip["contact_bits"]), dtype=np.uint8))
            contacts = bits[:clip["source_frames"] * 4].reshape(clip["source_frames"], 4).astype(bool)
            steps = 3
            for model_name, predictor in predictors.items():
                pose_history = raw["positions"][:24].copy()
                rotation_history = raw["rotations"][:24].copy()
                predicted_chunks = []
                chunk_errors = []
                teacher_forced_errors = []
                seam_jumps = []
                source_jumps = []
                for step in range(steps):
                    middle = 24 + 24 * step
                    end = middle + 24
                    root_history = raw["root_track"][middle - 24:middle]
                    root_future = raw["root_track"][middle:end]
                    visible = {"history_pose": pose_history, "history_rotations": rotation_history,
                               "history_root_local": root_local(root_history, root_history[-1]),
                               "future_root_plan_local": root_local(root_future, root_history[-1]),
                               "reference_pose": np.zeros((24, contract["bone_count"], 3), dtype=np.float32),
                               "reference_rotations": np.zeros((24, contract["bone_count"], 3, 3), dtype=np.float32),
                               "reference_frame_mask": np.zeros(24, dtype=np.float32)}
                    prediction = predictor.predict(visible)
                    pose = prediction["future_pose"]
                    rotation = prediction["future_rotations"]
                    target = raw["positions"][middle:end]
                    chunk_errors.append(float(np.sqrt(np.mean(np.sum((pose - target) ** 2, axis=-1))) * 100))
                    if step == 0:
                        teacher_forced_errors.append(chunk_errors[-1])
                    else:
                        teacher_visible = dict(visible,
                                               history_pose=raw["positions"][middle - 24:middle],
                                               history_rotations=raw["rotations"][middle - 24:middle])
                        teacher_pose = predictor.predict(teacher_visible)["future_pose"]
                        teacher_forced_errors.append(float(np.sqrt(np.mean(np.sum(
                            (teacher_pose - target) ** 2, axis=-1))) * 100))
                    seam = seam_metrics(pose_history, root_history, pose, root_future, target, root_future)
                    seam_jumps.append(seam["predicted_jump_cm"])
                    source_boundary = world_pose(raw["positions"][middle - 1:middle + 1],
                                                 raw["root_track"][middle - 1:middle + 1])
                    source_jumps.append(float(np.linalg.norm(source_boundary[1] - source_boundary[0],
                                                            axis=-1).mean() * 100))
                    predicted_chunks.append(pose)
                    pose_history = pose
                    rotation_history = rotation
                generated = np.concatenate(predicted_chunks)
                root = raw["root_track"][24:24 + 24 * steps]
                gt = raw["positions"][24:24 + 24 * steps]
                active = contacts[24:24 + 24 * steps]
                foot_speed, pairs = contact_speed(generated, root, active, feet, fps)
                source_speed, _ = contact_speed(gt, root, active, feet, fps)
                results.append({"clip_index": index, "asset": clip["asset"], "category": category,
                                "phase": labels["phase"], "style": labels["style"],
                                "model": model_name, "frames_generated": 24 * steps,
                                "chunk1_pose_rmse_cm": chunk_errors[0], "chunk2_pose_rmse_cm": chunk_errors[1],
                                "chunk3_pose_rmse_cm": chunk_errors[2],
                                "chunk2_teacher_forced_rmse_cm": teacher_forced_errors[1],
                                "chunk3_teacher_forced_rmse_cm": teacher_forced_errors[2],
                                "chunk3_closed_loop_penalty_cm": chunk_errors[2] - teacher_forced_errors[2],
                                "initial_seam_jump_cm": seam_jumps[0],
                                "replan_seam_jump_cm": float(np.mean(seam_jumps[1:])),
                                "source_replan_jump_cm": float(np.mean(source_jumps[1:])),
                                "contact_foot_speed_mps": foot_speed,
                                "source_contact_foot_speed_mps": source_speed,
                                "contact_pairs": pairs})
            print(f"rollout {index} {category}", flush=True)
    return results


def run_four_frame_rollouts(predictors, contract, manifest, feet):
    """Display four predicted frames, then replan using displayed history."""
    results = []
    source = Path(contract["source_dataset"])
    fps = contract["fps"]
    for category, indices in ROLLOUTS.items():
        for index in indices:
            clip = contract["clips"][index]
            labels = manifest["clips"][index]["labels"]
            if clip["split"] != "validation" or clip["category"] != category or clip["source_frames"] < 116:
                raise ValueError(f"Four-frame rollout needs 116 source frames: {index}")
            raw, _ = load_raw(source / clip["raw_file"], clip["source_frames"], contract["bone_count"], fps,
                              expected_sha256=clip["raw_sha256"])
            bits = np.unpackbits(np.frombuffer(__import__("base64").b64decode(clip["contact_bits"]), dtype=np.uint8))
            contacts = bits[:clip["source_frames"] * 4].reshape(clip["source_frames"], 4).astype(bool)
            for model_name, predictor in predictors.items():
                pose_history = raw["positions"][:24].copy()
                rotation_history = raw["rotations"][:24].copy()
                generated_chunks = []
                teacher_chunks = []
                replan_jumps = []
                source_jumps = []
                for step in range(18):
                    middle = 24 + 4 * step
                    root_history = raw["root_track"][middle - 24:middle]
                    root_future = raw["root_track"][middle:middle + 24]
                    visible = {"history_pose": pose_history, "history_rotations": rotation_history,
                               "history_root_local": root_local(root_history, root_history[-1]),
                               "future_root_plan_local": root_local(root_future, root_history[-1]),
                               "reference_pose": np.zeros((24, contract["bone_count"], 3), dtype=np.float32),
                               "reference_rotations": np.zeros((24, contract["bone_count"], 3, 3), dtype=np.float32),
                               "reference_frame_mask": np.zeros(24, dtype=np.float32)}
                    prediction = predictor.predict(visible)
                    shown_pose = prediction["future_pose"][:4]
                    shown_rotation = prediction["future_rotations"][:4]
                    generated_chunks.append(shown_pose)
                    if step == 0:
                        teacher_chunks.append(shown_pose)
                    else:
                        teacher_visible = dict(visible,
                                               history_pose=raw["positions"][middle - 24:middle],
                                               history_rotations=raw["rotations"][middle - 24:middle])
                        teacher_chunks.append(predictor.predict(teacher_visible)["future_pose"][:4])
                    seam = seam_metrics(pose_history, root_history, shown_pose, root_future[:4],
                                        raw["positions"][middle:middle + 4], root_future[:4])
                    replan_jumps.append(seam["predicted_jump_cm"])
                    source_boundary = world_pose(raw["positions"][middle - 1:middle + 1],
                                                 raw["root_track"][middle - 1:middle + 1])
                    source_jumps.append(float(np.linalg.norm(source_boundary[1] - source_boundary[0],
                                                            axis=-1).mean() * 100))
                    pose_history = np.concatenate((pose_history[4:], shown_pose))
                    rotation_history = np.concatenate((rotation_history[4:], shown_rotation))
                generated = np.concatenate(generated_chunks)
                teacher = np.concatenate(teacher_chunks)
                target = raw["positions"][24:96]
                root = raw["root_track"][24:96]
                active = contacts[24:96]
                def block_error(values, block):
                    section = slice(block * 24, (block + 1) * 24)
                    return float(np.sqrt(np.mean(np.sum((values[section] - target[section]) ** 2,
                                                    axis=-1))) * 100)
                foot_speed, pairs = contact_speed(generated, root, active, feet, fps)
                source_speed, _ = contact_speed(target, root, active, feet, fps)
                results.append({"clip_index": index, "asset": clip["asset"], "category": category,
                                "phase": labels["phase"], "style": labels["style"], "model": model_name,
                                "frames_generated": 72, "replan_every_frames": 4,
                                "block1_pose_rmse_cm": block_error(generated, 0),
                                "block2_pose_rmse_cm": block_error(generated, 1),
                                "block3_pose_rmse_cm": block_error(generated, 2),
                                "block2_teacher_forced_rmse_cm": block_error(teacher, 1),
                                "block3_teacher_forced_rmse_cm": block_error(teacher, 2),
                                "block3_closed_loop_penalty_cm": block_error(generated, 2) - block_error(teacher, 2),
                                "replan_seam_jump_cm": float(np.mean(replan_jumps[1:])),
                                "source_replan_jump_cm": float(np.mean(source_jumps[1:])),
                                "contact_foot_speed_mps": foot_speed,
                                "source_contact_foot_speed_mps": source_speed, "contact_pairs": pairs})
            print(f"four-frame rollout {index} {category}", flush=True)
    return results


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", action="append", metavar="NAME=PATH",
                        help="Override default checkpoints; repeat to compare multiple models")
    args = parser.parse_args()
    checkpoint_paths = CHECKPOINTS
    if args.checkpoint:
        checkpoint_paths = {}
        for item in args.checkpoint:
            name, separator, path = item.partition("=")
            if not separator or not name or not path or name in checkpoint_paths:
                parser.error("--checkpoint requires unique NAME=PATH values")
            checkpoint_paths[name] = Path(path)
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    predictors = {name: ConditionedPosePredictor(path, RELEASE, LOCK)
                  for name, path in checkpoint_paths.items()}
    first_name = next(iter(predictors))
    contract = predictors[first_name].contract
    manifest = json.loads((Path(contract["source_dataset"]) / "dataset.json").read_text(encoding="utf-8"))
    if any(predictor.config["contract_sha256"] != predictors[first_name].config["contract_sha256"]
           for predictor in predictors.values()):
        raise ValueError("Checkpoints use different contracts")
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in
            ("left_foot", "left_toe", "right_foot", "right_toe")]
    center = run_center_windows(predictors, contract, manifest, feet)
    rollouts = run_rollouts(predictors, contract, manifest, feet)
    four_frame = run_four_frame_rollouts(predictors, contract, manifest, feet)
    write_csv(args.output / "center_validation.csv", center)
    write_csv(args.output / "rollouts.csv", rollouts)
    write_csv(args.output / "rollouts_4frame.csv", four_frame)
    center_fields = ("non_anchor_pose_rmse_cm", "contact_foot_speed_mps",
                     "source_contact_foot_speed_mps", "predicted_jump_cm", "source_jump_cm",
                     "first_frame_error_cm", "causal_root_rmse_cm", "causal_root_end_error_cm",
                     "pose_change_under_causal_root_cm")
    rollout_fields = ("chunk1_pose_rmse_cm", "chunk2_pose_rmse_cm", "chunk3_pose_rmse_cm",
                      "chunk2_teacher_forced_rmse_cm", "chunk3_teacher_forced_rmse_cm",
                      "chunk3_closed_loop_penalty_cm",
                      "replan_seam_jump_cm", "source_replan_jump_cm",
                      "contact_foot_speed_mps", "source_contact_foot_speed_mps")
    summary = {
        "schema_version": 1,
        "split": "validation",
        "conditions": {"reference": "none", "oracle_root": "source future Root",
                       "causal_root": "past 6 Root increments constant translation and local yaw extrapolation",
                       "rollout_history": "generated pose and rotation after first 24 true history frames",
                       "rollout_root": "source future Root throughout"},
        "contract_sha256": predictors[first_name].config["contract_sha256"],
        "checkpoint_sha256": {name: file_sha256(path) for name, path in checkpoint_paths.items()},
        "source_manifest_sha256": contract["source_manifest_sha256"],
        "device": str(predictors[first_name].device),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "versions": {"python": platform.python_version(), "torch": torch.__version__,
                     "numpy": np.__version__, "scipy": scipy.__version__},
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "center_cases": len({row["clip_index"] for row in center}),
        "rollout_cases": len({row["clip_index"] for row in rollouts}),
        "four_frame_rollout_cases": len({row["clip_index"] for row in four_frame}),
        "center_by_category_model": {f"{category}/{model}": aggregate(
            [row for row in center if row["category"] == category and row["model"] == model], center_fields)
            for category in sorted(CORE) for model in checkpoint_paths},
        "rollout_by_category_model": {f"{category}/{model}": aggregate(
            [row for row in rollouts if row["category"] == category and row["model"] == model], rollout_fields)
            for category in sorted(CORE) for model in checkpoint_paths},
        "four_frame_by_category_model": {f"{category}/{model}": aggregate(
            [row for row in four_frame if row["category"] == category and row["model"] == model],
            ("block1_pose_rmse_cm", "block2_pose_rmse_cm", "block3_pose_rmse_cm",
             "block2_teacher_forced_rmse_cm", "block3_teacher_forced_rmse_cm",
             "block3_closed_loop_penalty_cm", "replan_seam_jump_cm", "source_replan_jump_cm",
             "contact_foot_speed_mps", "source_contact_foot_speed_mps"))
            for category in sorted(CORE) for model in checkpoint_paths},
        "limitations": ["No UE CMC/Mover trace or player input is available; causal Root is a past-only baseline, not actual controller output.",
                        "Contact bits are inferred from source motion and do not prove physical contact.",
                        "Rollouts use source future Root and only 12 fixed validation clips; cross-clip game transitions are untested.",
                        "Four-frame replanning always provides the next 24 source Root frames; this is not a causal controller.",
                        "The 24-frame model has no stance command input; Stand/Crouch switching is not evaluated here."]}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "center_cases": summary["center_cases"],
                      "rollout_cases": summary["rollout_cases"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
