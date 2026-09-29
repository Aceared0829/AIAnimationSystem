"""Pack causal CMC Root inputs for UE NNE inference and skinned rendering."""

import argparse
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


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_helper():
    spec = importlib.util.spec_from_file_location("cmc_root_eval", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_f32(folder, name, array):
    path = folder / name
    np.ascontiguousarray(array, dtype="<f4").tofile(path)
    return sha256(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--baseline-onnx", type=Path, required=True)
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
    models = {"baseline": args.baseline_onnx, "candidate": args.candidate_onnx}
    sessions = {name: ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
                for name, path in models.items()}
    trace = helper.read_trace(args.trace)
    args.output.mkdir(parents=True)
    save_f32(args.output, "mean.f32", mean)
    save_f32(args.output, "std.f32", std)
    shutil.copy2(Path(contract["source_dataset"]) / "skeleton.json", args.output / "skeleton.json")
    report = {"format": "ue_conditioned_cmc_fixture_v1", "contract_sha256":
              frozen["artifacts_sha256"]["contract/contract.json"],
              "trace_sha256": sha256(args.trace), "skeleton_sha256": sha256(args.output / "skeleton.json"),
              "axis_mapping": "data=(minus UE Y, UE Z, UE X)",
              "condition": "current CMC input held for 24 frames, accepted CMC history, no future source pose",
              "models": {name: {"onnx": str(path.resolve()), "sha256": sha256(path)}
                         for name, path in models.items()}, "scenarios": []}

    for label, (trace_name, index) in helper.SCENARIOS.items():
        clip = contract["clips"][index]
        raw, _ = load_raw(Path(contract["source_dataset"]) / clip["raw_file"],
                          clip["source_frames"], contract["bone_count"], contract["fps"],
                          expected_sha256=clip["raw_sha256"])
        source_trace = trace[trace_name]
        ground = source_trace["positions_cm"].copy()
        ground[:, 2] -= source_trace["half_heights_cm"]
        accepted = helper.align_to_source_root(ground, source_trace["quats"], raw["root_track"][0])
        proposed = accepted.copy()
        for start in (24, 48, 72):
            positions, quats = helper.command_plan(source_trace, start, helper.SPEED_CMPS[trace_name])
            positions[:, 2] += source_trace["half_heights_cm"][start] - source_trace["half_heights_cm"][start - 1]
            positions[:, 2] -= source_trace["half_heights_cm"][start]
            plan = helper.align_to_source_root(np.concatenate((ground[:1], positions)),
                                                np.concatenate((source_trace["quats"][:1], quats)),
                                                raw["root_track"][0])[1:]
            proposed[start:start + 24] = plan
        folder = args.output / label
        folder.mkdir()
        save_f32(folder, "accepted_root.f32", accepted[24:96])
        save_f32(folder, "command_plan.f32", proposed[24:96])
        save_f32(folder, "accepted_crouch.f32", source_trace["crouched"][24:96])
        entry = {"name": label, "clip_index": index, "asset": clip["asset"],
                 "source_raw_sha256": clip["raw_sha256"], "frames": 72, "windows": 3,
                 "crouch_accepted_frames": int(source_trace["crouched"][24:96].sum()),
                 "model_windows": {}}
        for name, session in sessions.items():
            history_pose = raw["positions"][:24].copy()
            history_rotation = raw["rotations"][:24].copy()
            windows = []
            for step, start in enumerate((24, 48, 72)):
                history_root = root_local(accepted[start - 24:start], accepted[start - 1])
                future_root = root_local(proposed[start:start + 24], accepted[start - 1])
                pos = ((history_pose - mean) / std).astype(np.float32)
                rot = history_rotation[..., :2].reshape(24, 79, 6).astype(np.float32)
                history = np.concatenate((np.concatenate((pos, rot), axis=-1).reshape(24, -1),
                                          history_root), axis=-1)[None]
                arrays = {"history": history, "root_plan": future_root[None],
                          "reference": np.zeros((1, 24, 711), dtype=np.float32),
                          "mask": np.zeros((1, 24, 1), dtype=np.float32)}
                expected, = session.run(None, arrays)
                if expected.shape != (1, 24, 711) or not np.isfinite(expected).all():
                    raise ValueError(f"invalid ONNX output: {label}/{name}/{step}")
                record = {"step": step, "inputs": {}, "output": f"{name}_{step}_expected.f32"}
                for field, values in arrays.items():
                    file = f"{name}_{step}_{field}.f32"
                    record["inputs"][field] = {"file": file, "sha256": save_f32(folder, file, values)}
                record["output_sha256"] = save_f32(folder, record["output"], expected)
                windows.append(record)
                decoded = expected[0].reshape(24, 79, 9)
                history_pose = decoded[..., :3] * std + mean
                history_rotation = rotation_6d_to_matrix(decoded[..., 3:])
            entry["model_windows"][name] = windows
        report["scenarios"].append(entry)
        print(f"packed {label}", flush=True)
    (args.output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "scenarios": len(report["scenarios"])},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
