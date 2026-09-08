"""把编辑器导出的动画批次转换为自有骨架的 MotionBricks 训练集。"""

import argparse
import json
import hashlib
import re
from pathlib import Path

import numpy as np
import torch

from motionbricks.data.unreal_dataset import contained_file, convert_clip, derive_motion_labels, read_json, skeleton_signature, training_bones, training_signature, UnrealSkeleton
from motionbricks.motionlib.core.motion_reps.dual_root_global_joints import DualRootGlobalJoints

MIN_TRAINING_FRAMES = 65

def prepare(source, output, skip_invalid=False, short_clip_policy="reject", native_fps=None, split=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if short_clip_policy not in {"reject", "hold"}:
        raise ValueError("短片段策略必须是 reject 或 hold")
    manifest = read_json(source / "manifest.json")
    if manifest.get("schema_version") != 1 or not manifest.get("clips"):
        raise ValueError("导出批次缺少有效清单")
    # 新目录避免覆盖已有训练数据；仅最后写 dataset.json，失败目录不会被识别为完整训练集。
    output.mkdir(parents=True, exist_ok=False)
    metadata, signature, total, sum_x, sum_x2 = None, None, 0, None, None
    clips, rejected, held_short_clips = [], [], []
    for index, filename in enumerate(manifest["clips"]):
        clip = None
        try:
            clip = read_json(contained_file(source, filename))
            if native_fps is not None and abs(clip["fps"] - native_fps) > 1e-6:
                continue
            positions, rotations, neutral = convert_clip(clip)
            source_frames = len(positions)
            timestamps = np.asarray(clip.get("timestamps_seconds", np.arange(source_frames) / clip["fps"]), dtype=np.float64)
            if timestamps.shape != (source_frames,) or not np.isfinite(timestamps).all() or abs(timestamps[0]) > 2e-6 or np.any(np.diff(timestamps) <= 0):
                raise ValueError("源时间戳必须逐帧严格递增")
            if not np.allclose(np.diff(timestamps), 1 / clip["fps"], atol=2e-6, rtol=1e-5):
                raise ValueError("不规则时间轴需要独立处理，不允许静默重采样")
            if clip.get("sampling_policy") == "source_data_keys":
                duration = clip.get("duration_seconds")
                if not isinstance(duration, (int, float)) or not np.isfinite(duration) or abs(timestamps[-1] - duration) > 2e-6:
                    raise ValueError("源采样键末帧必须对应原始时长")
            raw_positions, raw_rotations = positions.copy(), rotations.copy()
            if source_frames < MIN_TRAINING_FRAMES:
                if short_clip_policy != "hold":
                    raise ValueError(f"{filename} 特征无效或不足 {MIN_TRAINING_FRAMES} 帧；30 FPS 下请提供至少约 2.2 秒动画")
                padding = MIN_TRAINING_FRAMES - source_frames
                positions = np.concatenate([positions, np.repeat(positions[-1:], padding, axis=0)])
                rotations = np.concatenate([rotations, np.repeat(rotations[-1:], padding, axis=0)])
                held_short_clips.append({"file": filename, "asset": clip["asset"], "source_frames": source_frames, "training_frames": MIN_TRAINING_FRAMES})
            current_signature = skeleton_signature(clip)
            if signature is not None and signature != current_signature:
                raise ValueError(f"{filename} 的骨架、参考姿态、帧率或语义映射与本批次不一致；请分开导出")
            if signature is None:
                signature = current_signature
                metadata = {key: clip[key] for key in ("roles", "coordinate_system", "fps")}
                metadata["bones"] = training_bones(clip["bones"])
                metadata["neutral_joints"] = neutral.tolist()
                (output / "skeleton.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
                skeleton = UnrealSkeleton(output)
                representation = DualRootGlobalJoints(fps=clip["fps"], skeleton=skeleton, name="unreal_dual_root_global_joints")
            # 地面仍为 UE 的 Z=0；不自动把腾空动作落到地面。
            with torch.no_grad():
                features = representation({"posed_joints": torch.from_numpy(positions)[None], "global_joint_rots": torch.from_numpy(rotations)[None]},
                                          to_normalize=False, lengths=torch.tensor([len(positions)]))[0].numpy()
            if len(features) < MIN_TRAINING_FRAMES or not np.isfinite(features).all():
                raise ValueError(f"{filename} 特征无效或不足 {MIN_TRAINING_FRAMES} 帧；30 FPS 下请提供至少约 2.2 秒动画")
        except (OSError, ValueError, KeyError) as error:
            if not skip_invalid:
                raise
            rejected.append({"file": filename, "asset": clip.get("asset") if clip else None, "error": str(error)})
            continue
        # 同一目录下去掉末尾数字变体的动作家族只落入一个集合。
        group = re.sub(r"(?:_?\d+)+$", "", clip["asset"].split(".")[0].lower())
        bucket = int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) % 10
        partition = ("test" if bucket == 0 else "validation" if bucket == 1 else "train") if split else "train"
        if partition == "train":
            values = features[:source_frames].astype(np.float64)
            total += len(values)
            sum_x = values.sum(0) if sum_x is None else sum_x + values.sum(0)
            sum_x2 = (values ** 2).sum(0) if sum_x2 is None else sum_x2 + (values ** 2).sum(0)
        path = f"motion_{len(clips):05d}.npy"
        np.save(output / path, features)
        raw_path = f"raw_{len(clips):05d}.npz"
        np.savez_compressed(output / raw_path, positions=raw_positions, rotations=raw_rotations, timestamps=timestamps)
        clips.append({"file": path, "asset": clip["asset"], "frames": len(features), "source_frames": source_frames,
                      "raw_file": raw_path, "source_file": filename, "split": partition, "group": group,
                      "duration_seconds": clip.get("duration_seconds"), "sampling_policy": clip.get("sampling_policy", "legacy"),
                      "labels": derive_motion_labels(clip["asset"], source_frames)})
    if not clips:
        raise ValueError("没有通过特征与长度校验的动画，无法生成训练集")
    if total == 0:
        raise ValueError("划分后没有训练帧，不能使用留出集计算统计量；请检查动作家族分布")
    if rejected:
        (output / "rejected_clips.json").write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding="utf-8")
    if held_short_clips:
        (output / "held_short_clips.json").write_text(json.dumps(held_short_clips, ensure_ascii=False, indent=2), encoding="utf-8")
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
               "training_signature": training_signature(output), "clips": clips, "rejected_clips": len(rejected),
               "held_short_clips": len(held_short_clips), "short_clip_policy": short_clip_policy,
               "source": str(source), "split_policy": "asset_family_sha256_80_10_10" if split else "none", "stats_scope": "train_valid_frames"}
    (output / "dataset.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="包含 manifest.json 的 Unreal 导出目录")
    parser.add_argument("--output", required=True, help="必须尚不存在的训练集目录")
    parser.add_argument("--skip_invalid", action="store_true", help="记录并跳过不满足特征或训练窗口要求的片段")
    parser.add_argument("--native_fps", type=float, help="只处理此原生帧率组，不改变采样")
    parser.add_argument("--split", action="store_true", help="按动作家族划分独立留出集，统计量仅来自训练有效帧")
    parser.add_argument("--short_clip_policy", choices=("reject", "hold"), default="reject", help="短片段为 hold 时保持末帧至最小训练窗口")
    args = parser.parse_args()
    result = prepare(args.input, args.output, args.skip_invalid, args.short_clip_policy, args.native_fps, args.split)
    print(f"已准备 {len(result['clips'])} 段动画，每帧 {result['feature_dim']} 维；跳过 {result['rejected_clips']} 段，保持短片段 {result['held_short_clips']} 段。")
