"""按真实时间对照原始 UE 采样、FK 表示、旧模型和新模型；输出可离线播放的 HTML。"""
import argparse
import json
import hashlib
from pathlib import Path
from collections import defaultdict
import numpy as np
import torch
from evaluate_unreal_vqvae import load_vqvae, rotation_error_degrees
from motionbricks.helper.data_training_util import extract_feature_from_motion_rep


@torch.no_grad()
def decode_raw(net, rep, raw, keyframes="none", window_frames=0, bypass_quantizer=False):
    if window_frames and (window_frames < 8 or window_frames % 4):
        raise ValueError("重叠窗口必须是至少 8 帧的四倍数")
    positions = torch.from_numpy(raw["positions"].copy())[None]
    rotations = torch.from_numpy(raw["rotations"].copy())[None]
    count = positions.shape[1]
    frames = (count + 3) // 4 * 4
    ids = torch.arange(frames + 1).clamp_max(count - 1)
    global_motion, initial = rep({"posed_joints": positions[:, ids], "global_joint_rots": rotations[:, ids]}, to_normalize=True,
                                 lengths=torch.tensor([frames + 1]), return_init_heading_info=True)
    local = rep.dual_rep.global_to_local(global_motion, is_normalized=True, to_normalize=True, lengths=torch.tensor([frames + 1]))[:, :frames]
    cond = has_cond = None
    if keyframes != "none":
        has_cond = torch.zeros((1, frames), dtype=torch.bool)
        has_cond[:, 0] = True
        if keyframes == "ends":
            has_cond[:, count - 1] = True
        cond = local * has_cond[..., None]
    external = extract_feature_from_motion_rep(local, net.motion_rep, net.decoder_external_cond_feature_mode)
    if bypass_quantizer:
        if window_frames:
            raise ValueError("量化旁路诊断只支持整段模式")
        encoded = net.encoder(net.extract_feature(local, net.encoder_input_feature_mode).permute(0, 2, 1))
        target = net.extract_feature(cond, net.decoder_target_cond_feature_mode) if cond is not None else None
        result = net.decoder(encoded, external, target, has_cond).permute(0, 2, 1)
    elif window_frames and frames > window_frames:
        if window_frames < 8 or window_frames % 4:
            raise ValueError("重叠窗口必须是至少 8 帧的四倍数")
        starts = list(range(0, frames - window_frames + 1, window_frames // 2))
        if starts[-1] != frames - window_frames:
            starts.append(frames - window_frames)
        result = torch.zeros_like(local)
        weights = torch.zeros_like(local[..., :1])
        taper = torch.hann_window(window_frames, periodic=False).clamp_min(0.05)[None, :, None]
        for start in starts:
            end = start + window_frames
            decoded = net(local[:, start:end], target_cond=cond[:, start:end] if cond is not None else None,
                          has_target_cond=has_cond[:, start:end] if has_cond is not None else None, external_cond=external[:, start:end])["recon_state"]
            result[:, start:end] += decoded * taper
            weights[:, start:end] += taper
        # 先融合特征再完整积分一次；不使用真实根路径逐窗重置漂移。
        result = result / weights
    else:
        result = net(local, target_cond=cond, has_target_cond=has_cond, external_cond=external)["recon_state"]
    predicted = rep.dual_rep.local_motion_rep.inverse(result, is_normalized=True, init_heading_info=dict(initial))
    fk = rep.dual_rep.local_motion_rep.inverse(local, is_normalized=True, init_heading_info=dict(initial))
    ric = rep.dual_rep.local_motion_rep.inverse(local, is_normalized=True, joint_positions_from="ric_data", init_heading_info=dict(initial))
    # 恢复同一初始朝向和位置，再与未标准化的源姿态对照。
    reference = positions[0].numpy().copy()
    return reference, predicted["posed_joints"][0, :count].numpy(), predicted["global_joint_rots"][0, :count].numpy(), fk["posed_joints"][0, :count].numpy(), ric["posed_joints"][0, :count].numpy()


def measure(reference, predicted):
    error = predicted - reference
    rel = (predicted - predicted[:, :1]) - (reference - reference[:, :1])
    root = error[:, 0]
    return {"world_rmse_cm": float(np.sqrt(np.mean(np.sum(error**2, axis=-1))) * 100),
            "pose_rmse_cm": float(np.sqrt(np.mean(np.sum(rel**2, axis=-1))) * 100),
            "pose_p95_cm": float(np.quantile(np.linalg.norm(rel, axis=-1), .95) * 100),
            "root_horizontal_cm": float(np.sqrt(np.mean(np.sum(root[:, [0, 2]]**2, axis=-1))) * 100),
            "root_height_cm": float(np.sqrt(np.mean(root[:, 1]**2)) * 100),
            "root_initial_cm": float(np.linalg.norm(root[0]) * 100),
            "root_end_cm": float(np.linalg.norm(root[-1]) * 100)}


def evaluate(args):
    torch.set_num_threads(4)
    folder = Path(args.dataset)
    manifest = json.loads((folder / "dataset.json").read_text(encoding="utf8"))
    net, rep, contract = load_vqvae(args.checkpoint)
    if contract["signature"] != manifest["training_signature"]:
        raise ValueError("模型与评估数据集契约不一致")
    old = load_vqvae(args.baseline) if args.baseline else None
    manifest_hash = hashlib.sha256((folder / "dataset.json").read_bytes()).hexdigest()
    same_holdout = bool(old and all(c.get("config", {}).get("data", {}).get("manifest_sha256") == manifest_hash for c in (contract, old[2])))
    if old and old[1].fps != rep.fps:
        raise ValueError("禁止用不同帧率模型冒充原生对照")
    if old and (old[1].skeleton.bone_order_names_with_parents != rep.skeleton.bone_order_names_with_parents
                or not torch.allclose(old[1].skeleton.neutral_joints, rep.skeleton.neutral_joints, atol=1e-6, rtol=0)):
        raise ValueError("基线模型骨架或参考姿态不匹配；此评估不执行重定向")
    groups = defaultdict(list)
    for i, item in enumerate(manifest["clips"]):
        if item["split"] == args.split or args.split == "all":
            groups[item["labels"]["category"]].append(i)
    selected = []
    for category, ids in sorted(groups.items()):
        selected.extend(ids if args.per_category == 0 else [ids[j] for j in np.unique(np.linspace(0, len(ids) - 1, min(args.per_category, len(ids)), dtype=int))])
    samples, previews = [], []
    if not selected:
        raise ValueError("所选划分没有评估动作，不发布空报告")
    for i in selected:
        item = manifest["clips"][i]
        with np.load(folder / item["raw_file"]) as z:
            raw = {key: z[key] for key in z.files}
        ref, pred, rots, fk, ric = decode_raw(net, rep, raw, window_frames=args.window_frames)
        scores = measure(ref, pred)
        scores["rotation_mean_deg"] = float(rotation_error_degrees(raw["rotations"], rots).mean())
        report = {"asset": item["asset"], "split": item["split"], "category": item["labels"]["category"], "frames": len(ref), "new": scores,
                  "representation_fk": measure(ref, fk), "representation_positions": measure(ref, ric)}
        old_pred = None
        if old:
            _, old_pred, old_rots, _, _ = decode_raw(old[0], old[1], raw, window_frames=args.window_frames)
            report["old"] = measure(ref, old_pred)
            report["old"]["rotation_mean_deg"] = float(rotation_error_degrees(raw["rotations"], old_rots).mean())
        # 先给每类一个展示，再用完整定量集合汇总，避免只展示低误差动作。
        preview_group = item["labels"]["category"]
        if preview_group == "Traversal":
            from motionbricks.data.unreal_dataset import derive_motion_labels
            preview_group += "/" + derive_motion_labels(item["asset"])["action"]
        if not any(p["preview_group"] == preview_group for p in previews) or len(selected) <= 6:
            entry = {"name": item["labels"]["asset_name"], "category": item["labels"]["category"], "split": item["split"], "fps": manifest["fps"],
                     "preview_group": preview_group,
                     "time": raw["timestamps"].tolist(), "ref": ref.round(5).tolist(), "pred": pred.round(5).tolist(), "scores": report}
            if old_pred is not None:
                entry["old"] = old_pred.round(5).tolist()
            else:
                entry["fk"] = fk.round(5).tolist()
            for mode in ("first", "ends"):
                _, conditioned, _, _, _ = decode_raw(net, rep, raw, mode, window_frames=args.window_frames)
                report[mode] = measure(ref, conditioned)
                entry[mode] = conditioned.round(5).tolist()
            previews.append(entry)
        samples.append(report)
        print(f"{len(samples)}/{len(selected)} {item['labels']['category']}: pose={scores['pose_rmse_cm']:.2f} cm", flush=True)
    aggregate = {}
    for model in ("new", "old", "representation_fk", "representation_positions"):
        values = [s[model] for s in samples if model in s]
        if values:
            aggregate[model] = {key: float(np.mean([v[key] for v in values])) for key in values[0]}
    report = {"checkpoint": str(Path(args.checkpoint).resolve()), "dataset": str(folder.resolve()), "fps": manifest["fps"], "split": args.split,
              "training_steps": contract.get("global_step"), "baseline_steps": old[2].get("global_step") if old else None,
              "same_holdout_verified": same_holdout,
              "pose_aware_sampling": contract.get("config", {}).get("model", {}).get("args", {}).get("pose_aware_sampling", False),
              "baseline_checkpoint": str(Path(args.baseline).resolve()) if args.baseline else None,
              "aggregation": "unweighted mean of per-clip metrics", "window_frames": args.window_frames, "sample_count": len(samples), "aggregate": aggregate, "samples": samples,
              "limitations": ["VQ 编码重建已知动作，不是文本生成。", "新模型留出集按资产名称家族划分，原始录制来源未知，无法保证录制级独立。",
                              "新旧模型使用同一原生数据集的训练分区；本轮没有改变划分。" if same_holdout else "旧基线未验证采用相同留出集；其对照不能解释为独立测试成绩。",
                              "保留骨盆及其后代；非骨盆 UE root、曲线、事件和 additive 不在本次模型输出范围。",
                              "FK 固定骨长不能精确表达所有辅助骨平移；位置特征另行检查。", "骨架预览不是 UE 实际蒙皮角色验收。"]}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    skeleton = json.loads((folder / "skeleton.json").read_text(encoding="utf8"))
    payload = {"parents": [b["parent"] for b in skeleton["bones"]], "previews": previews, "report": report}
    (output / "gallery.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--output", required=True)
    parser.add_argument("--split", choices=["train", "validation", "test", "all"], default="test")
    parser.add_argument("--per_category", type=int, default=0)
    parser.add_argument("--window_frames", type=int, default=0, help="0 为整段推理；否则重叠融合特征后一次积分根轨迹")
    evaluate(parser.parse_args())
