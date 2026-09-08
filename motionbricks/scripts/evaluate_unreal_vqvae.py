"""评估 UE 动画 VQ-VAE 的无关键帧重建，并导出骨架对照 GIF。

该工具评估的是码本对已知动作的重建质量：根运动作为外部条件保留，不输入姿态关键帧。
它不是文本生成或 UE 运行时推理的视觉验收；报告会明确保留这一边界。
"""

import argparse
import json
from pathlib import Path

import imageio.v3 as iio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from hydra.utils import instantiate
from omegaconf import OmegaConf

from motionbricks.data.unreal_dataset import UnrealMotionDataset, derive_motion_labels, read_json, training_signature
from motionbricks.helper.data_training_util import extract_feature_from_motion_rep
from motionbricks.helper.pl_util import load_motion_rep

plt.rcParams["font.family"] = "Microsoft YaHei"


def load_vqvae(checkpoint_path):
    checkpoint_path = Path(checkpoint_path).resolve()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint.get("unreal_contract", {}).get("kind") != "vqvae":
        raise ValueError("检查点不是受 UE 数据契约保护的 VQ-VAE")
    conf = OmegaConf.create(checkpoint["unreal_contract"]["config"])
    if training_signature(conf.data.folder) != checkpoint["unreal_contract"]["signature"]:
        raise ValueError("检查点引用的骨架或统计量已改变")
    if Path(conf.skeleton.folder).resolve() != Path(conf.data.folder).resolve() or Path(conf.motion_rep.stats.folder).resolve() != (Path(conf.data.folder) / "stats").resolve():
        raise ValueError("检查点骨架和统计量路径必须属于同一数据集")
    motion_rep = load_motion_rep(conf)
    pose_net = instantiate(conf.model.pose_vqvae_network, motion_rep=motion_rep.dual_rep.local_motion_rep)
    prefix = "pose_net."
    state = {key[len(prefix):]: value for key, value in checkpoint["state_dict"].items() if key.startswith(prefix)}
    pose_net.load_state_dict(state, strict=True)
    pose_net.eval()
    return pose_net, motion_rep, {**checkpoint["unreal_contract"], "global_step": checkpoint.get("global_step")}


def reconstruct(pose_net, motion_rep, motion):
    """不使用姿态关键帧，仅保留训练定义中的稠密根条件。"""
    frames = len(motion) // 4 * 4
    if frames < 4:
        raise ValueError("动作帧数不足以通过四倍下采样的 VQ-VAE")
    global_motion = motion[:frames][None]
    lengths = torch.tensor([frames])
    local_motion = motion_rep.dual_rep.global_to_local(global_motion, is_normalized=True, to_normalize=True, lengths=lengths)
    external_cond = extract_feature_from_motion_rep(local_motion, pose_net.motion_rep, pose_net.decoder_external_cond_feature_mode)
    with torch.no_grad():
        reconstruction = pose_net(local_motion, target_cond=None, has_target_cond=None, external_cond=external_cond)["recon_state"]
    reference = motion_rep.dual_rep.local_motion_rep.inverse(local_motion, is_normalized=True, return_quat=False)
    predicted = motion_rep.dual_rep.local_motion_rep.inverse(reconstruction, is_normalized=True, return_quat=False)
    return reference, predicted


def rotation_error_degrees(reference_rotations, reconstructed_rotations):
    delta = np.matmul(np.swapaxes(reference_rotations, -1, -2), reconstructed_rotations)
    cosine = np.clip((np.trace(delta, axis1=-2, axis2=-1) - 1.0) * 0.5, -1.0, 1.0)
    return np.degrees(np.arccos(cosine))


def metrics(reference, predicted):
    ref_positions = reference["posed_joints"][0].cpu().numpy()
    pred_positions = predicted["posed_joints"][0].cpu().numpy()
    position_error = np.linalg.norm(ref_positions - pred_positions, axis=-1)
    rotation_error = rotation_error_degrees(reference["global_joint_rots"][0].cpu().numpy(), predicted["global_joint_rots"][0].cpu().numpy())
    root_error = np.linalg.norm(ref_positions[:, 0] - pred_positions[:, 0], axis=-1)
    return {"position_rmse_m": float(np.sqrt(np.mean(position_error ** 2))), "position_p95_m": float(np.quantile(position_error, 0.95)),
            "rotation_mean_deg": float(np.mean(rotation_error)), "rotation_p95_deg": float(np.quantile(rotation_error, 0.95)),
            "root_path_rmse_m": float(np.sqrt(np.mean(root_error ** 2)))}


def draw_skeleton(axis, positions, parents, title, color, bounds):
    axis.cla()
    for joint, parent in enumerate(parents):
        if parent >= 0:
            points = positions[[joint, parent]]
            axis.plot(points[:, 0], points[:, 1], points[:, 2], color=color, linewidth=2.0)
    axis.scatter(positions[:, 0], positions[:, 1], positions[:, 2], color=color, s=7)
    axis.set(xlim=bounds[0], ylim=bounds[1], zlim=bounds[2], title=title)
    axis.set_box_aspect((1, 1, 1.45))
    axis.view_init(elev=14, azim=-62)
    axis.set_axis_off()


def render_gif(reference, predicted, parents, title, output, fps, max_frames=45):
    reference, predicted = reference[0].cpu().numpy(), predicted[0].cpu().numpy()
    # 姿态预览逐帧根对齐；根位移保留在报告的 root_path_rmse_m 中单独评估。
    reference = reference - reference[:, :1]
    predicted = predicted - predicted[:, :1]
    all_positions = np.concatenate([reference, predicted], axis=0)
    low, high = all_positions.reshape(-1, 3).min(axis=0), all_positions.reshape(-1, 3).max(axis=0)
    center = (low + high) * 0.5
    radius = max(float(np.max(high - low)) * 0.58, 0.7)
    bounds = tuple((center[index] - radius, center[index] + radius) for index in range(3))
    selected, durations = preview_timing(len(reference), fps, max_frames)
    figure = plt.figure(figsize=(8, 4.4), dpi=110)
    reference_axis, predicted_axis = figure.add_subplot(1, 2, 1, projection="3d"), figure.add_subplot(1, 2, 2, projection="3d")
    frames = []
    for frame in selected:
        draw_skeleton(reference_axis, reference[frame], parents, "参考姿态（根对齐）", "#2D74DA", bounds)
        draw_skeleton(predicted_axis, predicted[frame], parents, "VQ 重建（根对齐、无姿态关键帧）", "#E87B22", bounds)
        figure.suptitle(f"{title}  |  姿态视图  frame {frame + 1}/{len(reference)}", fontsize=10)
        figure.canvas.draw()
        frames.append(np.asarray(figure.canvas.buffer_rgba())[:, :, :3].copy())
    plt.close(figure)
    iio.imwrite(output, np.stack(frames), duration=durations.tolist(), loop=0)


def preview_timing(frame_count, fps, max_frames):
    """抽帧只减少图像数量，保留相邻代表帧之间的源时间间隔。"""
    if max_frames < 2 or frame_count < 2 or not np.isfinite(fps) or fps <= 0:
        raise ValueError("预览至少需要两帧且帧率必须为正")
    selected = np.unique(np.linspace(0, frame_count - 1, min(frame_count, max_frames), dtype=int))
    return selected, np.diff(np.append(selected, frame_count)) * 1000 / fps


def find_samples(dataset, categories):
    result = []
    for category in categories:
        category = category.lower()
        exact_category = [(index, item) for index, item in enumerate(dataset.manifest["clips"])
                          if (item.get("labels") or derive_motion_labels(item["asset"], item.get("source_frames")))["category"].lower() == category]
        if exact_category:
            index, item = exact_category[0]
            result.append((index, item.get("labels") or derive_motion_labels(item["asset"], item.get("source_frames"))))
            continue
        for index, item in enumerate(dataset.manifest["clips"]):
            labels = item.get("labels") or derive_motion_labels(item["asset"], item.get("source_frames"))
            if labels["action"] == category or labels["category"].lower() == category:
                result.append((index, labels))
                break
    if not result:
        raise ValueError("没有找到与请求类别匹配的动画")
    return result


def main(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    dataset = UnrealMotionDataset(args.dataset)
    pose_net, motion_rep, contract = load_vqvae(args.checkpoint)
    if contract.get("signature") != dataset.manifest["training_signature"]:
        raise ValueError("VQ-VAE 检查点和待评估数据集的骨架或统计量契约不匹配")
    skeleton = read_json(Path(args.dataset) / "skeleton.json")
    parents = [bone["parent"] for bone in skeleton["bones"]]
    reports = []
    for index, labels in find_samples(dataset, args.categories):
        reference, predicted = reconstruct(pose_net, motion_rep, dataset[index]["motion"])
        result = {"dataset_index": index, "asset": dataset.manifest["clips"][index]["asset"], "split": dataset.manifest["clips"][index].get("split", "unknown"), "labels": labels, **metrics(reference, predicted)}
        filename = f"{len(reports) + 1:02d}_{labels['action']}_reconstruction.gif"
        render_gif(reference["posed_joints"], predicted["posed_joints"], parents, labels["description_zh"], output / filename, dataset.manifest["fps"], args.max_preview_frames)
        result["preview"] = filename
        reports.append(result)
    aggregate = {key: float(np.mean([item[key] for item in reports])) for key in ("position_rmse_m", "position_p95_m", "rotation_mean_deg", "rotation_p95_deg", "root_path_rmse_m")}
    report = {"evaluation_type": "VQ-VAE selected feature-window reconstruction without pose keyframes", "limitations": ["按类别选择代表动作，未限定留出分区；逐段 split 见 samples。", "参考为训练特征的固定骨长 FK 还原，不是原始 UE 位置。", "此工具裁剪到四帧对齐的特征窗口，短动作可能包含存储补齐；原生时间评估请使用 evaluate_native_quality.py。", "根运动作为外部条件保留；此结果不代表无条件或文本生成质量。", "GIF 是独立骨架重建预览，不是 Unreal 运行时画面。"],
              "checkpoint": str(Path(args.checkpoint).resolve()), "dataset": str(Path(args.dataset).resolve()), "aggregate": aggregate, "samples": reports}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# UE 动画 VQ-VAE 视觉重建评估", "", "本报告评估已知动作的无姿态关键帧重建；它不等同于文本生成或 UE 运行时视觉验收。", "", "## 平均误差", "",
             f"- 关节位置 RMSE：{aggregate['position_rmse_m']:.3f} m", f"- 关节位置 P95：{aggregate['position_p95_m']:.3f} m", f"- 全局旋转平均误差：{aggregate['rotation_mean_deg']:.1f}°", f"- 全局旋转 P95：{aggregate['rotation_p95_deg']:.1f}°", f"- 根轨迹 RMSE：{aggregate['root_path_rmse_m']:.3f} m", "", "## 样本"]
    for item in reports:
        lines.extend(["", f"### {item['labels']['description_zh']}", f"- 资产：`{item['asset']}`", f"- 预览：`{item['preview']}`", f"- 位置 RMSE：{item['position_rmse_m']:.3f} m；旋转平均误差：{item['rotation_mean_deg']:.1f}°"])
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--categories", nargs="+", default=["walk", "crouch", "jump", "climb"])
    parser.add_argument("--max_preview_frames", type=int, default=45, help="每个 GIF 最多渲染的代表帧数")
    main(parser.parse_args())
