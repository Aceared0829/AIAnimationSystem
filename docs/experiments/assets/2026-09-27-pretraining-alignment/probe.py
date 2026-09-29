"""Read-only CPU checks for the pretraining proposal; no weight updates."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from scipy.spatial.transform import Rotation


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    skeleton = json.loads((args.bundle / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    result = {
        "type": "read_only_cpu_contract_probe",
        "numpy": np.__version__,
        "onnxruntime": ort.__version__,
        "provider": "CPUExecutionProvider",
        "contract_sha256": sha256(args.contract),
        "bundle_manifest_sha256": sha256(args.bundle / "manifest.json"),
        "source_basis": [],
        "rotation_feedback": [],
        "limitations": [
            "Three diagnostic train clips, not dataset-wide direction coverage.",
            "Body heading is an upper-body position proxy, not authoritative facing.",
            "One synthetic constant-plan call per model; no UE or closed-loop result.",
            "Rotation differences are dimensionless, not angles or pose errors.",
        ],
    }
    for index in (1299, 1313, 446):
        clip = next(row for row in contract["clips"] if row["clip_index"] == index)
        path = Path(contract["source_dataset"]) / clip["raw_file"]
        digest = sha256(path)
        if digest != clip["raw_sha256"]:
            raise ValueError(f"Changed source clip: {path}")
        with np.load(path, allow_pickle=False) as raw:
            velocity = Rotation.from_quat(raw["root_track"][:-1, 3:]).inv().apply(
                np.diff(raw["root_track"][:, :3], axis=0) * contract["fps"]
            )
            velocity = velocity[:, [2, 0, 1]] * [1, -1, 1]
            pose = raw["positions"][..., [2, 0, 1]] * [1, -1, 1]
            forward = np.cross(
                pose[:, names.index("upperarm_r")] - pose[:, names.index("upperarm_l")],
                pose[:, names.index("spine_03")] - pose[:, names.index("pelvis")],
            )
            yaw = np.rad2deg(np.arctan2(forward[:, 1], forward[:, 0]))
            result["source_basis"].append({
                "clip_index": index,
                "asset": clip["asset"],
                "split": clip["split"],
                "raw_sha256": digest,
                "frames": len(pose),
                "velocity_root_ue_median_mps": np.median(velocity, axis=0).tolist(),
                "body_yaw_proxy_median_degrees": float(np.median(yaw)),
            })
    seed = np.fromfile(args.bundle / "seed_pose.f32", np.float32).reshape(24, 711)
    roots = np.zeros((24, 7), np.float32)
    roots[:, 6] = 1
    history = np.concatenate((seed, roots), axis=-1)[None]
    plan = roots.copy()
    plan[:, 2] = np.arange(1, 25, dtype=np.float32) * 2 / 30
    result["probe_condition"] = {
        "seed_clip": 446, "fps": 30, "future_pose_reference": False,
        "root_plan": "synthetic +UE-X in model root basis, 2 m/s, times 1/30..24/30",
        "history_root": "24 identical identity transforms",
        "rotation_samples_per_model": 4 * 79,
        "seed_sha256": sha256(args.bundle / "seed_pose.f32"),
    }
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    for model in ("control", "speed_phase"):
        path = args.bundle / f"model_{model}.onnx"
        session = ort.InferenceSession(str(path), sess_options=options,
                                       providers=["CPUExecutionProvider"])
        output = session.run(None, {
            "history": history, "root_plan": plan[None],
            "reference": np.zeros((1, 24, 711), np.float32),
            "mask": np.zeros((1, 24, 1), np.float32),
        })[0].reshape(24, 79, 9)
        rotation = output[:4, :, 3:]
        first, second = rotation[..., [0, 2, 4]], rotation[..., [1, 3, 5]]
        norm = np.linalg.norm(first, axis=-1, keepdims=True)
        if np.any(norm <= 1e-6):
            raise ValueError("Degenerate first rotation column")
        first = first / norm
        second = second - np.sum(first * second, axis=-1, keepdims=True) * first
        norm = np.linalg.norm(second, axis=-1, keepdims=True)
        if np.any(norm <= 1e-6):
            raise ValueError("Degenerate second rotation column")
        second = second / norm
        canonical = np.stack((first, second), axis=-1).reshape(4, 79, 6)
        difference = np.abs(rotation - canonical)
        result["rotation_feedback"].append({
            "model": model, "onnx_sha256": sha256(path),
            "abs_mean": float(difference.mean()), "abs_max": float(difference.max()),
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "rotation_feedback": result["rotation_feedback"]}))


if __name__ == "__main__":
    main()
