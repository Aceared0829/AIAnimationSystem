"""在站蹲早期过渡窗口上诊断旧条件模型的无参考姿态误差。"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

from data.runtime.conditioned_motion import sha256
from data.runtime.stance_motion import load_stance_window
from motionbricks.data.unreal_dataset import read_json
from training.pretrain.train_conditioned_pose import ReferenceGuidedPose
from training.pretrain.train_stance_pilot import StanceGuidedPose


def pack_pose(positions, rotations, mean, std):
    normalized = (positions - mean) / std
    sixd = rotations[..., :2].reshape(*rotations.shape[:2], 6)
    return np.concatenate((normalized, sixd), axis=-1).reshape(len(positions), -1).astype(np.float32)


@torch.no_grad()
def evaluate(checkpoint_path, stance_folder, output, *, split="test", base_override=None, source_override=None,
             pilot_checkpoint_path=None, selection="transition"):
    stance_folder = Path(stance_folder)
    contract = read_json(stance_folder / "contract.json")
    base_folder = Path(base_override if base_override is not None else contract["base_contract"])
    base = read_json(base_folder / "contract.json")
    if sha256(base_folder / "contract.json") != contract["base_contract_sha256"]:
        raise ValueError("v2 与来源 v1 契约哈希不一致")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    config = checkpoint["config"]
    if config["contract_sha256"] != contract["base_contract_sha256"]:
        raise ValueError("旧模型检查点不是该 v2 索引的来源契约")
    stats = base["stats"]["pose_m"]
    mean_path = base_folder / "stats" / stats["mean"]
    std_path = base_folder / "stats" / stats["std"]
    if sha256(mean_path) != stats["mean_sha256"] or sha256(std_path) != stats["std_sha256"]:
        raise ValueError("姿态统计量哈希不匹配")
    mean, std = np.load(mean_path), np.load(std_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ReferenceGuidedPose(contract["bone_count"], config["width"]).to(device)
    model.load_state_dict(checkpoint["model"])
    model.eval()
    pilot = None
    if pilot_checkpoint_path is not None:
        pilot_checkpoint = torch.load(pilot_checkpoint_path, map_location="cpu", weights_only=False)
        pilot_config = pilot_checkpoint["config"]
        if pilot_config["stance_contract_sha256"] != sha256(stance_folder / "contract.json"):
            raise ValueError("状态模型检查点不是该 v2 索引的训练结果")
        if pilot_config["base_contract_sha256"] != contract["base_contract_sha256"]:
            raise ValueError("状态模型来源 v1 契约不匹配")
        if pilot_config["initialize_checkpoint_sha256"] != sha256(checkpoint_path):
            raise ValueError("状态模型不是从所比较的旧模型初始化")
        if split == "test" and any(base["clips"][index]["split"] == "test"
                                   for index in pilot_config["train_clip_indices"]):
            raise ValueError("状态模型训练使用了冻结测试片段")
        pilot = StanceGuidedPose(contract["bone_count"], config["width"]).to(device)
        pilot.load_state_dict(pilot_checkpoint["model"])
        pilot.eval()
    per_clip = defaultdict(list)
    with (stance_folder / "windows.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if selection == "transition" and not row["future_contains_transition"]:
                continue
            sample = load_stance_window(stance_folder, row, contract=contract, base_override=base_folder,
                                        source_override=source_override)
            if sample["metadata"]["split"] != split:
                continue
            visible, target = sample["input"], sample["target"]
            history = pack_pose(visible["history_pose"], visible["history_rotations"], mean, std)
            history = np.concatenate((history, visible["history_root_local"]), axis=-1)
            root = visible["future_root_plan_local"]
            zeros = torch.zeros(1, 24, contract["bone_count"] * 9, device=device)
            mask = torch.zeros(1, 24, 1, device=device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                predicted = model(torch.from_numpy(history[None]).to(device),
                                  torch.from_numpy(root[None]).to(device), zeros, mask)
                pilot_predicted = (pilot(torch.from_numpy(history[None]).to(device),
                                         torch.from_numpy(root[None]).to(device), zeros, mask,
                                         torch.from_numpy(visible["goal_stance_proxy"][None]).to(device))
                                   if pilot is not None else None)
            predicted_position = predicted.float().cpu().numpy().reshape(24, contract["bone_count"], 9)[..., :3] * std + mean
            target_position = target["future_pose"]
            hold_position = np.repeat(visible["history_pose"][-1:], 24, axis=0)
            joint_error_cm = np.sqrt(np.mean(np.sum((predicted_position - target_position) ** 2, axis=-1))) * 100
            hold_error_cm = np.sqrt(np.mean(np.sum((hold_position - target_position) ** 2, axis=-1))) * 100
            detail = {"start": row["start"], "model_joint_rmse_cm": float(joint_error_cm),
                      "hold_joint_rmse_cm": float(hold_error_cm),
                      "transition_frames": int(np.sum(target["observed_stance"] == 2))}
            if pilot_predicted is not None:
                pilot_position = (pilot_predicted.float().cpu().numpy()
                                  .reshape(24, contract["bone_count"], 9)[..., :3] * std + mean)
                detail["pilot_joint_rmse_cm"] = float(np.sqrt(np.mean(np.sum(
                    (pilot_position - target_position) ** 2, axis=-1))) * 100)
            per_clip[row["clip_index"]].append(detail)
    clips = []
    for index, windows in sorted(per_clip.items()):
        clip = {"clip_index": index, "asset": base["clips"][index]["asset"], "windows": len(windows),
                "model_joint_rmse_cm": float(np.mean([row["model_joint_rmse_cm"] for row in windows])),
                "hold_joint_rmse_cm": float(np.mean([row["hold_joint_rmse_cm"] for row in windows])),
                "details": windows}
        if pilot is not None:
            clip["pilot_joint_rmse_cm"] = float(np.mean([row["pilot_joint_rmse_cm"] for row in windows]))
        clips.append(clip)
    report = {"checkpoint_sha256": sha256(checkpoint_path), "stance_contract_sha256": sha256(stance_folder / "contract.json"),
              "base_contract_sha256": contract["base_contract_sha256"], "split": split,
              "selection": ("all_windows_whose_future_intersects_provisional_transition"
                            if selection == "transition" else "all_indexed_windows"),
              "root_condition": "source_future_oracle", "references": "none", "device": str(device),
              "metric": "mean_of_per_window_joint_euclidean_rmse_cm_then_equal_clip_average",
              "clips": clips, "clip_count": len(clips), "window_count": sum(row["windows"] for row in clips),
              "model_joint_rmse_cm": float(np.mean([row["model_joint_rmse_cm"] for row in clips])) if clips else None,
              "hold_joint_rmse_cm": float(np.mean([row["hold_joint_rmse_cm"] for row in clips])) if clips else None,
              "limitations": ["过渡区间是骨盆高度代理边界；仅四条已知方向动作。",
                              "目标状态从旧动画推定；不存在真实玩家按键或 CMC 批准记录。",
                              "使用原动作未来 Root；不衡量在线规划、碰撞或脚部接触。"]}
    if pilot is not None:
        report["pilot_checkpoint_sha256"] = sha256(pilot_checkpoint_path)
        report["pilot_joint_rmse_cm"] = (float(np.mean([row["pilot_joint_rmse_cm"] for row in clips]))
                                         if clips else None)
        report["pilot_condition"] = "inferred_goal_proxy_from_source_animation"
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--stance-contract", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--split", choices=("train", "validation", "test"), default="test")
    parser.add_argument("--base-contract-override")
    parser.add_argument("--source-override")
    parser.add_argument("--pilot-checkpoint", help="可选：与旧模型在同一窗口比较的状态条件检查点")
    parser.add_argument("--selection", choices=("transition", "all"), default="transition")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.checkpoint, args.stance_contract, args.output, split=args.split,
                              base_override=args.base_contract_override, source_override=args.source_override,
                              pilot_checkpoint_path=args.pilot_checkpoint, selection=args.selection),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
