"""把编辑器导出的动画批次转换为自有骨架的 MotionBricks 训练集。"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from motionbricks.data.unreal_dataset import contained_file, convert_clip, read_json, skeleton_signature, training_signature, UnrealSkeleton
from motionbricks.motionlib.core.motion_reps.dual_root_global_joints import DualRootGlobalJoints


def prepare(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    manifest = read_json(source / "manifest.json")
    if manifest.get("schema_version") != 1 or not manifest.get("clips"):
        raise ValueError("导出批次缺少有效清单")
    # 新目录避免覆盖已有训练数据；仅最后写 dataset.json，失败目录不会被识别为完整训练集。
    output.mkdir(parents=True, exist_ok=False)
    metadata, signature, total, sum_x, sum_x2 = None, None, 0, None, None
    clips = []
    for index, filename in enumerate(manifest["clips"]):
        clip = read_json(contained_file(source, filename))
        positions, rotations, neutral = convert_clip(clip)
        current_signature = skeleton_signature(clip)
        if signature is None:
            signature = current_signature
            metadata = {key: clip[key] for key in ("bones", "roles", "coordinate_system", "fps")}
            metadata["neutral_joints"] = neutral.tolist()
            (output / "skeleton.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
            skeleton = UnrealSkeleton(output)
            representation = DualRootGlobalJoints(fps=clip["fps"], skeleton=skeleton, name="unreal_dual_root_global_joints")
        elif signature != current_signature:
            raise ValueError(f"{filename} 的骨架、参考姿态、帧率或语义映射与本批次不一致；请分开导出")
        # 地面仍为 UE 的 Z=0；不自动把腾空动作落到地面。
        with torch.no_grad():
            features = representation({"posed_joints": torch.from_numpy(positions)[None], "global_joint_rots": torch.from_numpy(rotations)[None]},
                                      to_normalize=False, lengths=torch.tensor([len(positions)]))[0].numpy()
        if len(features) < 65 or not np.isfinite(features).all():
            raise ValueError(f"{filename} 特征无效或不足 65 帧；30 FPS 下请提供至少约 2.2 秒动画")
        values = features.astype(np.float64)
        total += len(values)
        sum_x = values.sum(0) if sum_x is None else sum_x + values.sum(0)
        sum_x2 = (values ** 2).sum(0) if sum_x2 is None else sum_x2 + (values ** 2).sum(0)
        path = f"motion_{index:05d}.npy"
        np.save(output / path, features)
        clips.append({"file": path, "asset": clip["asset"], "frames": len(features)})
    mean = (sum_x / total).astype(np.float32)
    std = np.sqrt(np.maximum(sum_x2 / total - (sum_x / total) ** 2, 0)).astype(np.float32)
    stats = output / "stats"
    stats.mkdir()
    np.save(stats / "mean.npy", mean)
    np.save(stats / "std.npy", std)
    indices = representation.indices["global_rep"]
    for item in clips:
        path = output / item["file"]
        features = np.load(path, allow_pickle=False)
        normalized = ((features - mean) / np.sqrt(std ** 2 + 1e-5))[:, indices]
        np.save(path, normalized.astype(np.float32))
    dataset = {"schema_version": 1, "fps": metadata["fps"], "feature_dim": len(indices), "skeleton_signature": signature,
               "training_signature": training_signature(output), "clips": clips}
    (output / "dataset.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="包含 manifest.json 的 Unreal 导出目录")
    parser.add_argument("--output", required=True, help="必须尚不存在的训练集目录")
    args = parser.parse_args()
    result = prepare(args.input, args.output)
    print(f"已准备 {len(result['clips'])} 段动画，每帧 {result['feature_dim']} 维。")
