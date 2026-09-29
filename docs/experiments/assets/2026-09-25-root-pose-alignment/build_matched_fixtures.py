"""Build paired Root/pose fixtures for the UE four-way sliding diagnosis."""

import argparse
import base64
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np
import onnxruntime as ort

from data.runtime.conditioned_motion import load_raw, root_local
from inference.runtime.conditioned_pose import rotation_6d_to_matrix
from training.pretrain.train_conditioned_pose import verify_release


ROOT = Path(__file__).resolve().parents[4]
RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
HELPER = ROOT / "docs/experiments/assets/2026-09-25-closed-loop-optimization/evaluate_cmc_root.py"
CASES = {"walk": (1587, 0), "run": (1109, 0), "crouch": (146, 0)}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_f32(folder, name, values):
    path = folder / name
    np.ascontiguousarray(values, dtype="<f4").tofile(path)
    return sha256(path)


def load_helper():
    spec = importlib.util.spec_from_file_location("cmc_root_eval", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--candidate-onnx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    helper = load_helper()
    contract, frozen = verify_release(RELEASE, LOCK)
    stats = contract["stats"]["pose_m"]
    mean = np.load(RELEASE / "contract/stats" / stats["mean"]).astype(np.float32)
    std = np.load(RELEASE / "contract/stats" / stats["std"]).astype(np.float32)
    traces = helper.read_trace(args.trace)
    session = ort.InferenceSession(str(args.candidate_onnx), providers=["CPUExecutionProvider"])
    args.output.mkdir(parents=True)
    save_f32(args.output, "mean.f32", mean)
    save_f32(args.output, "std.f32", std)
    shutil.copy2(Path(contract["source_dataset"]) / "skeleton.json", args.output / "skeleton.json")
    report = {"schema_version": 1, "format": "ue_root_pose_four_way_v1", "trace_sha256": sha256(args.trace),
              "contract_sha256": frozen["artifacts_sha256"]["contract/contract.json"],
              "onnx_sha256": sha256(args.candidate_onnx), "cases": []}

    for label, (index, offset) in CASES.items():
        clip = contract["clips"][index]
        if clip["split"] != ("train" if label == "run" else "validation") or offset + 96 > clip["source_frames"]:
            raise ValueError(f"invalid selected window: {label}/{index}/{offset}")
        raw, _ = load_raw(Path(contract["source_dataset"]) / clip["raw_file"],
                          clip["source_frames"], contract["bone_count"], contract["fps"],
                          expected_sha256=clip["raw_sha256"])
        source = raw["root_track"][offset:offset + 96]
        trace = traces[label]
        ground = trace["positions_cm"].copy()
        ground[:, 2] -= trace["half_heights_cm"]
        accepted = helper.align_to_source_root(ground, trace["quats"], source[0])
        planned = accepted.copy()
        for start in (24, 48, 72):
            # 这一组 CMC 在固定平地上匀速移动且保持朝向，当前已执行速度足以因果预测 24 帧。
            velocity = trace["velocities_cmps"][start - 1]
            positions = trace["positions_cm"][start - 1] + np.arange(1, 25)[:, None] * velocity[None] / 30
            positions[:, 2] -= trace["half_heights_cm"][start - 1]
            quats = np.repeat(trace["quats"][start - 1:start], 24, axis=0)
            planned[start:start + 24] = helper.align_to_source_root(
                np.concatenate((ground[:1], positions)), np.concatenate((trace["quats"][:1], quats)), source[0])[1:]
        folder = args.output / label
        folder.mkdir()
        save_f32(folder, "source_root.f32", source[24:96])
        save_f32(folder, "accepted_root.f32", accepted[24:96])
        save_f32(folder, "command_plan.f32", planned[24:96])
        source_pose = np.concatenate((((raw["positions"][offset + 24:offset + 96] - mean) / std),
                                      raw["rotations"][offset + 24:offset + 96, ..., :2].reshape(72, 79, 6)), axis=-1)
        save_f32(folder, "source_pose.f32", source_pose)
        contact_bits = np.unpackbits(np.frombuffer(base64.b64decode(clip["contact_bits"]), dtype=np.uint8))
        contacts = contact_bits[:clip["source_frames"] * 4].reshape(clip["source_frames"], 4)
        save_f32(folder, "source_contacts.f32", contacts[offset + 24:offset + 96])
        history_pose = raw["positions"][offset:offset + 24].copy()
        history_rotation = raw["rotations"][offset:offset + 24].copy()
        windows = []
        for step, start in enumerate((24, 48, 72)):
            history_root = root_local(accepted[start - 24:start], accepted[start - 1])
            future_root = root_local(planned[start:start + 24], accepted[start - 1])
            history_bones = np.concatenate((((history_pose - mean) / std),
                                            history_rotation[..., :2].reshape(24, 79, 6)), axis=-1).reshape(24, -1)
            history = np.concatenate((history_bones, history_root), axis=-1)[None].astype(np.float32)
            arrays = {"history": history, "root_plan": future_root[None],
                      "reference": np.zeros((1, 24, 711), dtype=np.float32),
                      "mask": np.zeros((1, 24, 1), dtype=np.float32)}
            expected, = session.run(None, arrays)
            if expected.shape != (1, 24, 711) or not np.isfinite(expected).all():
                raise ValueError(f"invalid prediction: {label}/{step}")
            for field, values in arrays.items():
                save_f32(folder, f"candidate_{step}_{field}.f32", values)
            save_f32(folder, f"candidate_{step}_expected.f32", expected)
            windows.append({"step": step, "output_sha256": sha256(folder / f"candidate_{step}_expected.f32")})
            decoded = expected[0].reshape(24, 79, 9)
            history_pose = decoded[..., :3] * std + mean
            history_rotation = rotation_6d_to_matrix(decoded[..., 3:])
        source_velocity = np.diff(source[:, :3], axis=0) * 30
        actual_velocity = np.diff(accepted[:, :3], axis=0) * 30
        root_plan_error_cm = np.linalg.norm(planned[24:96, :3] - accepted[24:96, :3], axis=1) * 100
        report["cases"].append({"scenario": label, "clip_index": index, "offset": offset, "split": clip["split"],
                                "asset": clip["asset"], "source_raw_sha256": clip["raw_sha256"],
                                "source_speed_mps": float(np.linalg.norm(source_velocity, axis=1).mean()),
                                "cmc_speed_mps": float(np.linalg.norm(actual_velocity, axis=1).mean()),
                                "source_cmc_velocity_gap_mps": float(np.linalg.norm(source_velocity - actual_velocity, axis=1).mean()),
                                "root_plan_error_mean_cm": float(root_plan_error_cm.mean()),
                                "root_plan_error_max_cm": float(root_plan_error_cm.max()),
                                "windows": windows})
        print(f"packed matched {label}: {report['cases'][-1]['source_cmc_velocity_gap_mps']:.3f} m/s velocity gap", flush=True)
    (args.output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
