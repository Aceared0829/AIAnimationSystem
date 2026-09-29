"""Replay real UE CMC traces and compare a causal command-held Root plan."""

import argparse
import csv
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
SCENARIOS = {"walk": ("walk", 1306), "run": ("run", 983), "crouch": ("crouch", 49),
             "stand_to_crouch": ("crouch", 1306)}
SPEED_CMPS = {"walk": 140., "run": 400., "crouch": 80.}
# Match the frozen dataset's UE_TO_MOTION axes: data X = -UE Y.
UE_TO_DATA = np.array([[0., -1., 0.], [0., 0., 1.], [1., 0., 0.]])


def read_trace(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    result = {}
    for scenario in ("walk", "run", "crouch"):
        chosen = [row for row in rows if row["scenario"] == scenario]
        if len(chosen) != 96 or [int(row["frame"]) for row in chosen] != list(range(96)):
            raise ValueError(f"incomplete CMC trace: {scenario}")
        positions = np.array([[float(row[f"capsule_{axis}_cm"]) for axis in "xyz"]
                              for row in chosen], dtype=np.float64)
        quats = np.array([[float(row[f"quat_{axis}"]) for axis in "xyzw"]
                          for row in chosen], dtype=np.float64)
        velocities = np.array([[float(row[f"velocity_{axis}_cmps"]) for axis in "xyz"]
                               for row in chosen], dtype=np.float64)
        half_heights = np.array([float(row["capsule_half_height_cm"]) for row in chosen], dtype=np.float64)
        inputs = np.array([[float(row["input_x"]), float(row["input_y"])]
                           for row in chosen], dtype=np.float64)
        modes = np.array([int(row["movement_mode"]) for row in chosen])
        crouched = np.array([int(row["is_crouched"]) for row in chosen])
        if not np.isfinite(positions).all() or not np.isfinite(quats).all() or (modes != 1).any():
            raise ValueError(f"nonfinite or non-walking trace: {scenario}")
        result[scenario] = {"positions_cm": positions, "quats": quats,
                            "half_heights_cm": half_heights,
                            "velocities_cmps": velocities, "inputs": inputs,
                            "crouched": crouched}
    return result


def align_to_source_root(ue_positions, ue_quats, source_first):
    source_rotation = Rotation.from_quat(source_first[3:])
    initial_ue_rotation = Rotation.from_quat(ue_quats[0])
    relative_position = initial_ue_rotation.inv().apply(ue_positions - ue_positions[0]) / 100
    mapped_position = (UE_TO_DATA @ relative_position.T).T
    data_positions = source_first[:3] + source_rotation.apply(mapped_position)
    relative_ue_rotation = initial_ue_rotation.inv() * Rotation.from_quat(ue_quats)
    matrices = UE_TO_DATA @ relative_ue_rotation.as_matrix() @ UE_TO_DATA.T
    data_quats = (source_rotation * Rotation.from_matrix(matrices)).as_quat()
    return np.concatenate((data_positions, data_quats), axis=-1).astype(np.float32)


def command_plan(trace, start, speed_cap, fps=30):
    """Use only accepted history and the current frame's command, held for 24 frames."""
    position = trace["positions_cm"][start - 1].copy()
    velocity = trace["velocities_cmps"][start - 1].copy()
    orientation = Rotation.from_quat(trace["quats"][start - 1])
    command = trace["inputs"][start].copy()
    norm = float(np.linalg.norm(command))
    command = command / norm if norm > 1e-6 else command
    desired = np.array([command[0], command[1], 0.]) * speed_cap
    output_positions = []
    output_quats = []
    for _ in range(24):
        delta = desired - velocity
        step = min(float(np.linalg.norm(delta)), 2048. / fps)
        if np.linalg.norm(delta) > 1e-6:
            velocity += delta / np.linalg.norm(delta) * step
        position += velocity / fps
        if np.linalg.norm(velocity[:2]) > 1e-5:
            current_yaw = orientation.as_euler("xyz")[2]
            target_yaw = float(np.arctan2(velocity[1], velocity[0]))
            delta_yaw = (target_yaw - current_yaw + np.pi) % (2 * np.pi) - np.pi
            next_yaw = current_yaw + np.clip(delta_yaw, -np.deg2rad(720) / fps,
                                             np.deg2rad(720) / fps)
            orientation = Rotation.from_euler("z", next_yaw)
        output_positions.append(position.copy())
        output_quats.append(orientation.as_quat())
    return np.array(output_positions), np.array(output_quats)


def run_model(predictor, raw, accepted_root, planned_root):
    history_pose = raw["positions"][:24].copy()
    history_rotations = raw["rotations"][:24].copy()
    parts = []
    for step in range(3):
        start = 24 + step * 24
        root_history = accepted_root[start - 24:start]
        future_plan = planned_root[start:start + 24]
        output = predictor.predict({
            "history_pose": history_pose, "history_rotations": history_rotations,
            "history_root_local": root_local(root_history, root_history[-1]),
            "future_root_plan_local": root_local(future_plan, root_history[-1]),
            "reference_pose": np.zeros((24, predictor.contract["bone_count"], 3), dtype=np.float32),
            "reference_rotations": np.zeros((24, predictor.contract["bone_count"], 3, 3), dtype=np.float32),
            "reference_frame_mask": np.zeros(24, dtype=np.float32)})
        history_pose = output["future_pose"]
        history_rotations = output["future_rotations"]
        parts.append(history_pose)
    return np.concatenate(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--checkpoint", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    paths = {}
    for item in args.checkpoint:
        name, separator, path = item.partition("=")
        if not separator or name in paths or not name or not path:
            parser.error("checkpoint requires unique NAME=PATH")
        paths[name] = Path(path)
    predictors = {name: ConditionedPosePredictor(path, RELEASE, LOCK) for name, path in paths.items()}
    contract = next(iter(predictors.values())).contract
    traces = read_trace(args.trace)
    summary = {"trace_sha256": hashlib.sha256(args.trace.read_bytes()).hexdigest(),
               "trace_source": "UE 5.8.2 AIAnimation.Lab.CMCRootCapture automation test, 30 Hz",
               "pose_root": "CMC capsule bottom = actor location minus current capsule half-height; UE cm mapped to data m",
               "future_plan_modes": ["accepted_replay_upper_bound", "command_held_causal_proxy"],
               "checkpoints": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for name, path in paths.items()}, "scenarios": []}
    for label, (trace_name, index) in SCENARIOS.items():
        clip = contract["clips"][index]
        raw, _ = load_raw(Path(contract["source_dataset"]) / clip["raw_file"],
                          clip["source_frames"], contract["bone_count"], contract["fps"],
                          expected_sha256=clip["raw_sha256"])
        trace = traces[trace_name]
        accepted_ground = trace["positions_cm"].copy()
        accepted_ground[:, 2] -= trace["half_heights_cm"]
        accepted = align_to_source_root(accepted_ground, trace["quats"], raw["root_track"][0])
        proposed = accepted.copy()
        root_errors = []
        for start in (24, 48, 72):
            positions, quats = command_plan(trace, start, SPEED_CMPS[trace_name])
            # CMC has processed the stance request before animation planning, so the accepted half-height is available.
            positions[:, 2] += trace["half_heights_cm"][start] - trace["half_heights_cm"][start - 1]
            positions[:, 2] -= trace["half_heights_cm"][start]
            local = align_to_source_root(np.concatenate((accepted_ground[:1], positions)),
                                         np.concatenate((trace["quats"][:1], quats)),
                                         raw["root_track"][0])[1:]
            proposed[start:start + 24] = local
            root_errors.append(float(np.linalg.norm(local[-1, :3] - accepted[start + 23, :3]) * 100))
        record = {"scenario": label, "clip_index": index,
                  "command_root_end_error_cm_by_block": root_errors,
                  "crouch_accepted_frames": int(trace["crouched"].sum()),
                  "models": {}}
        saved = {"accepted_root": accepted[24:96], "command_root_plan": proposed[24:96],
                 "accepted_crouch": trace["crouched"][24:96], "player_input": trace["inputs"][24:96]}
        for mode, plan in (("accepted_replay", accepted), ("command_plan", proposed)):
            for name, predictor in predictors.items():
                pose = run_model(predictor, raw, accepted, plan)
                world = apply_authoritative_root(pose, accepted[24:96])
                if not np.isfinite(pose).all() or not np.isfinite(world).all():
                    raise ValueError(f"nonfinite model output: {label}/{mode}/{name}")
                first_history = apply_authoritative_root(raw["positions"][23:24], accepted[23:24])[0]
                seam_cm = float(np.linalg.norm(world[0] - first_history, axis=-1).mean() * 100)
                key = f"{mode}_{name}"
                record["models"][key] = {"first_seam_jump_cm": seam_cm,
                                          "max_joint_abs_m": float(np.abs(pose).max()), "finite": True}
                saved[f"pose_{key}"] = pose
        np.savez_compressed(args.output / f"{label}_cmc_root.npz", **saved)
        summary["scenarios"].append(record)
        print(f"CMC {label}: root end errors {root_errors}", flush=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
