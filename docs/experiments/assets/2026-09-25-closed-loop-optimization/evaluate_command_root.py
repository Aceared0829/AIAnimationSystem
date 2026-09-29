"""No-oracle-Root scripted-control proxy for conditioned-pose closed-loop inference.

The planner integrates explicit speed/turn commands. It is not UE CMC/Mover,
and source frames after the first 24 are not read by the planner or predictor.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.conditioned_motion import load_raw, root_local
from inference.runtime.conditioned_pose import ConditionedPosePredictor
from motionbricks.data.unreal_dataset import apply_authoritative_root


ROOT = Path(__file__).resolve().parents[4]
RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
SCRIPTS = {
    "walk": (1306, ((1.4, 0.), (1.2, 90.), (0., 0.)), 4.0),
    "run": (983, ((4.0, 0.), (3.5, -120.), (0., 0.)), 8.0),
    "crouch": (49, ((0.8, 0.), (0.7, 60.), (0., 0.)), 3.0),
}


def integrate(initial_root, initial_speed, commands, accel, fps=30):
    current = initial_root.copy()
    rotation = Rotation.from_quat(current[3:])
    speed = float(initial_speed)
    yaw_rate = 0.0
    frames = []
    for target_speed, target_yaw_degrees in commands:
        target_yaw = np.deg2rad(target_yaw_degrees)
        for _ in range(24):
            delta = np.clip(target_speed - speed, -accel / fps, accel / fps)
            speed += float(delta)
            yaw_rate += float(np.clip(target_yaw - yaw_rate, -np.deg2rad(360) / fps,
                                      np.deg2rad(360) / fps))
            rotation = rotation * Rotation.from_rotvec([0., yaw_rate / fps, 0.])
            current[:3] += rotation.apply([0., 0., speed / fps]).astype(np.float32)
            current[3:] = rotation.as_quat().astype(np.float32)
            frames.append(current.copy())
    return np.array(frames, dtype=np.float32)


def predict(predictor, history_pose, history_rotations, history_root, planned_root):
    poses = []
    rotations = []
    for step in range(3):
        future = planned_root[step * 24:(step + 1) * 24]
        visible = {"history_pose": history_pose, "history_rotations": history_rotations,
                   "history_root_local": root_local(history_root, history_root[-1]),
                   "future_root_plan_local": root_local(future, history_root[-1]),
                   "reference_pose": np.zeros((24, predictor.contract["bone_count"], 3), dtype=np.float32),
                   "reference_rotations": np.zeros((24, predictor.contract["bone_count"], 3, 3), dtype=np.float32),
                   "reference_frame_mask": np.zeros(24, dtype=np.float32)}
        result = predictor.predict(visible)
        history_pose = result["future_pose"]
        history_rotations = result["future_rotations"]
        history_root = future
        poses.append(history_pose)
        rotations.append(history_rotations)
    return np.concatenate(poses), np.concatenate(rotations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    paths = {}
    for entry in args.checkpoint:
        name, separator, path = entry.partition("=")
        if not separator or not name or not path or name in paths:
            parser.error("checkpoints require unique NAME=PATH")
        paths[name] = Path(path)
    predictors = {name: ConditionedPosePredictor(path, RELEASE, LOCK) for name, path in paths.items()}
    contract = next(iter(predictors.values())).contract
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = (names.index("foot_l"), names.index("foot_r"))
    results = {"source_condition": "first 24 source frames only; scripted speed/yaw commands; no future source Root",
               "planner": "kinematic acceleration and yaw-rate integration, not CMC/Mover",
               "checkpoints": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for name, path in paths.items()}, "scenarios": []}
    for label, (index, commands, accel) in SCRIPTS.items():
        clip = contract["clips"][index]
        raw, _ = load_raw(Path(contract["source_dataset"]) / clip["raw_file"],
                          clip["source_frames"], contract["bone_count"], contract["fps"],
                          expected_sha256=clip["raw_sha256"])
        history_root = raw["root_track"][:24]
        speed = float(np.linalg.norm(np.diff(history_root[-7:, :3], axis=0), axis=-1).mean() * 30)
        planned_root = integrate(history_root[-1], speed, commands, accel)
        record = {"scenario": label, "initial_clip_index": index,
                  "scripted_commands_speed_mps_yaw_degps": commands,
                  "root_translation_m": (planned_root[-1, :3] - history_root[-1, :3]).tolist(),
                  "models": {}}
        saved = {"root": planned_root}
        for name, predictor in predictors.items():
            pose, rotations = predict(predictor, raw["positions"][:24],
                                      raw["rotations"][:24], history_root, planned_root)
            world = apply_authoritative_root(pose, planned_root)
            if not np.isfinite(pose).all() or not np.isfinite(rotations).all():
                raise ValueError(f"nonfinite controlled rollout: {label}/{name}")
            foot_velocity = np.linalg.norm(np.diff(world[:, feet], axis=0), axis=-1) * 30
            source_history_world = apply_authoritative_root(raw["positions"][22:24], history_root[22:24])
            first_jump = np.linalg.norm(world[0] - source_history_world[-1], axis=-1).mean() * 100
            record["models"][name] = {"first_seam_jump_cm": float(first_jump),
                                       "mean_foot_speed_mps_all_frames": float(foot_velocity.mean()),
                                       "max_joint_abs_m": float(np.abs(pose).max()),
                                       "finite": True}
            saved[f"pose_{name}"] = pose
            saved[f"rotations_{name}"] = rotations
        np.savez_compressed(args.output / f"{label}_scripted_root.npz", **saved)
        results["scenarios"].append(record)
        print(f"controlled {label}: {record['root_translation_m']}", flush=True)
    (args.output / "summary.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
