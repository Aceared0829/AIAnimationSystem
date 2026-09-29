"""Build an auditable local bundle for the live UE player probe."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from data.runtime.conditioned_motion import load_raw
from training.pretrain.train_conditioned_pose import verify_release


ROOT = Path(__file__).resolve().parents[3]
RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
SEED_INDEX = 446
EXPECTED_CONTRACT = "9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d"


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def save_f32(path, values):
    np.ascontiguousarray(values, dtype="<f4").tofile(path)
    return digest(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-onnx", type=Path, required=True)
    parser.add_argument("--candidate-onnx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    contract, frozen = verify_release(RELEASE, LOCK)
    contract_hash = frozen["artifacts_sha256"]["contract/contract.json"]
    if contract_hash != EXPECTED_CONTRACT or contract["fps"] != 30 or contract["bone_count"] != 79:
        raise ValueError("Unexpected source contract")
    seed = contract["clips"][SEED_INDEX]
    if seed["split"] != "train" or seed["category"] != "Idle" or seed["source_frames"] < 24:
        raise ValueError("Invalid standing idle seed")
    raw, raw_hash = load_raw(Path(contract["source_dataset"]) / seed["raw_file"],
                             seed["source_frames"], 79, 30, expected_sha256=seed["raw_sha256"])
    stats = contract["stats"]["pose_m"]
    mean = np.load(RELEASE / "contract/stats" / stats["mean"]).astype(np.float32)
    std = np.load(RELEASE / "contract/stats" / stats["std"]).astype(np.float32)
    seed_pose = np.concatenate((((raw["positions"][:24] - mean) / std),
                                raw["rotations"][:24, ..., :2].reshape(24, 79, 6)), axis=-1)
    if seed_pose.shape != (24, 79, 9) or not np.isfinite(seed_pose).all():
        raise ValueError("Invalid idle pose seed")

    args.output.mkdir(parents=True)
    copied = {
        "model_control.onnx": args.control_onnx,
        "model_speed_phase.onnx": args.candidate_onnx,
        "skeleton.json": Path(contract["source_dataset"]) / "skeleton.json",
    }
    hashes = {}
    for name, source in copied.items():
        shutil.copyfile(source, args.output / name)
        hashes[name] = digest(args.output / name)
    hashes["mean.f32"] = save_f32(args.output / "mean.f32", mean)
    hashes["std.f32"] = save_f32(args.output / "std.f32", std)
    hashes["seed_pose.f32"] = save_f32(args.output / "seed_pose.f32", seed_pose)
    report = {"schema_version": 1, "format": "ai_animation_live_player_probe_v1",
              "contract_sha256": contract_hash, "seed_clip_index": SEED_INDEX,
              "seed_asset": seed["asset"], "seed_split": seed["split"],
              "seed_raw_sha256": raw_hash, "history_frames": 24,
              "future_frames": 24, "sampling_fps": 30, "bones": 79,
              "future_pose_reference": False, "source_future_root": False,
              "files_sha256": hashes}
    (args.output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"bundle": str(args.output.resolve()), "manifest": report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
