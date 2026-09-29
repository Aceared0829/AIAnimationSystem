"""Diagnostic foot-lock/2-bone IK comparison on generated 72-frame rollouts.

The source-contact variant is an oracle upper bound. The heuristic variant uses
only generated ankle positions, a floor height, and past generated frames.
Rotations are intentionally not rewritten, so neither output is UE-ready.
"""

import argparse
import base64
import csv
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
CLIPS = {"Walk": (1306, 1420, 1486, 1675),
         "Run": (983, 836, 913, 1077),
         "Crouch": (49, 154, 201, 376)}


def predict72(predictor, contract, raw):
    parts = []
    pose_history = raw["positions"][:24].copy()
    rotation_history = raw["rotations"][:24].copy()
    for chunk in range(3):
        start = 24 + 24 * chunk
        roots_before = raw["root_track"][start - 24:start]
        roots_future = raw["root_track"][start:start + 24]
        prediction = predictor.predict({
            "history_pose": pose_history, "history_rotations": rotation_history,
            "history_root_local": root_local(roots_before, roots_before[-1]),
            "future_root_plan_local": root_local(roots_future, roots_before[-1]),
            "reference_pose": np.zeros((24, contract["bone_count"], 3), dtype=np.float32),
            "reference_rotations": np.zeros((24, contract["bone_count"], 3, 3), dtype=np.float32),
            "reference_frame_mask": np.zeros(24, dtype=np.float32)})
        pose_history = prediction["future_pose"]
        rotation_history = prediction["future_rotations"]
        parts.append(pose_history)
    return np.concatenate(parts)


def heuristic_contacts(world, feet, floor_y):
    observed = np.zeros((len(world), 2), dtype=bool)
    for leg, foot in enumerate(feet):
        planted = False
        for frame in range(len(world)):
            height = world[frame, foot, 1] - floor_y
            speed = (np.linalg.norm(world[frame, foot] - world[frame - 1, foot]) * 30
                     if frame else 0.0)
            if planted:
                planted = height <= 0.18 and speed <= 2.0
            else:
                planted = height <= 0.12 and speed <= 1.3
            observed[frame, leg] = planted
    return observed


def solve_knee(hip, old_knee, old_ankle, target, upper, lower):
    axis = target - hip
    distance = float(np.linalg.norm(axis))
    if distance < 1e-5:
        return old_knee, old_ankle
    axis /= distance
    reach = max(upper + lower - 1e-4, 1e-4)
    minimum = max(abs(upper - lower) + 1e-4, 1e-4)
    used_distance = np.clip(distance, minimum, reach)
    reached = hip + axis * used_distance
    along = (upper * upper - lower * lower + used_distance * used_distance) / (2 * used_distance)
    out = float(np.sqrt(max(upper * upper - along * along, 0.0)))
    bend = old_knee - hip - np.dot(old_knee - hip, axis) * axis
    bend_norm = float(np.linalg.norm(bend))
    if bend_norm < 1e-5:
        bend = old_knee - old_ankle
        bend -= np.dot(bend, axis) * axis
        bend_norm = float(np.linalg.norm(bend))
    if bend_norm < 1e-5:
        bend = np.cross(axis, [0., 1., 0.])
        bend_norm = float(np.linalg.norm(bend))
    if bend_norm < 1e-5:
        bend = np.cross(axis, [1., 0., 0.])
        bend_norm = float(np.linalg.norm(bend))
    knee = hip + along * axis + out * bend / max(bend_norm, 1e-5)
    return knee, reached


def correct(world, contacts, legs, source_world):
    corrected = world.copy()
    anchors = [None, None]
    active = [False, False]
    corrections = []
    for frame in range(len(world)):
        for leg, (hip, knee, foot, toe) in enumerate(legs):
            planted = bool(contacts[frame, leg])
            if not planted:
                anchors[leg], active[leg] = None, False
                continue
            if not active[leg]:
                anchors[leg], active[leg] = world[frame, foot].copy(), True
            upper = float(np.median(np.linalg.norm(source_world[:, hip] - source_world[:, knee], axis=-1)))
            lower = float(np.median(np.linalg.norm(source_world[:, knee] - source_world[:, foot], axis=-1)))
            new_knee, new_foot = solve_knee(world[frame, hip], world[frame, knee],
                                             world[frame, foot], anchors[leg], upper, lower)
            correction = new_foot - world[frame, foot]
            corrected[frame, knee] = new_knee
            corrected[frame, foot] = new_foot
            corrected[frame, toe] += correction
            corrections.append(float(np.linalg.norm(correction)))
    return corrected, corrections


def contact_speed(world, contacts, feet):
    velocities = np.linalg.norm(np.diff(world[:, feet], axis=0), axis=-1) * 30
    paired = contacts[1:] & contacts[:-1]
    return float(velocities[paired].mean()) if paired.any() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    predictor = ConditionedPosePredictor(args.checkpoint, RELEASE, LOCK)
    contract = predictor.contract
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    legs = [(names.index(name + "_l"), names.index("calf_l"), names.index("foot_l"), names.index("ball_l"))
            for name in ("thigh",)] + [
            (names.index("thigh_r"), names.index("calf_r"), names.index("foot_r"), names.index("ball_r"))]
    feet = [leg[2] for leg in legs]
    rows = []
    for category, indices in CLIPS.items():
        for index in indices:
            clip = contract["clips"][index]
            raw, _ = load_raw(Path(contract["source_dataset"]) / clip["raw_file"],
                              clip["source_frames"], contract["bone_count"], contract["fps"],
                              expected_sha256=clip["raw_sha256"])
            bits = np.unpackbits(np.frombuffer(base64.b64decode(clip["contact_bits"]), dtype=np.uint8))
            oracle = bits[:clip["source_frames"] * 4].reshape(-1, 4)[24:96, [0, 2]].astype(bool)
            pose = predict72(predictor, contract, raw)
            roots = raw["root_track"][24:96]
            source_world = apply_authoritative_root(raw["positions"][24:96], roots)
            world = apply_authoritative_root(pose, roots)
            history_world = apply_authoritative_root(raw["positions"][:24], raw["root_track"][:24])
            floor_y = float(np.quantile(history_world[:, feet, 1], 0.08) - 0.08)
            detected = heuristic_contacts(world, feet, floor_y)
            for mode, contacts in (("none", np.zeros_like(oracle)), ("oracle_contact", oracle),
                                   ("causal_heuristic", detected)):
                adjusted, corrections = correct(world, contacts, legs, source_world)
                lengths = []
                source_lengths = []
                for hip, knee, foot, _ in legs:
                    lengths.extend((np.linalg.norm(adjusted[:, hip] - adjusted[:, knee], axis=-1),
                                    np.linalg.norm(adjusted[:, knee] - adjusted[:, foot], axis=-1)))
                    source_lengths.extend((np.linalg.norm(source_world[:, hip] - source_world[:, knee], axis=-1),
                                           np.linalg.norm(source_world[:, knee] - source_world[:, foot], axis=-1)))
                bone_error = np.mean([np.abs(a - np.median(b)).mean() for a, b in zip(lengths, source_lengths)])
                rows.append({"category": category, "clip_index": index, "mode": mode,
                             "pose_rmse_cm": float(np.sqrt(np.mean(np.sum((adjusted - source_world) ** 2,
                                                                          axis=-1))) * 100),
                             "source_contact_foot_speed_mps": contact_speed(adjusted, oracle, feet),
                             "source_foot_speed_mps": contact_speed(source_world, oracle, feet),
                             "bone_length_error_cm": float(bone_error * 100),
                             "mean_foot_correction_cm": float(np.mean(corrections) * 100) if corrections else 0.0,
                             "max_foot_correction_cm": float(np.max(corrections) * 100) if corrections else 0.0,
                             "detected_contact_fraction": float(contacts.mean()),
                             "contact_precision_vs_source": float((detected & oracle).sum() /
                                                                  max(detected.sum(), 1)) if mode == "causal_heuristic" else None,
                             "contact_recall_vs_source": float((detected & oracle).sum() /
                                                               max(oracle.sum(), 1)) if mode == "causal_heuristic" else None})
                if index in (1306, 983, 49) and mode != "none":
                    rotation = Rotation.from_quat(roots[:, 3:])
                    local = np.einsum("tij,tbj->tbi", rotation.inv().as_matrix(),
                                      adjusted - roots[:, None, :3]).astype(np.float32)
                    np.savez_compressed(args.output / f"{category.lower()}_{index}_{mode}.npz",
                                        positions=local, roots=roots, contacts=contacts)
            print(f"evaluated {category} {index}", flush=True)
    with (args.output / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(args.output / "results.csv")


if __name__ == "__main__":
    main()
