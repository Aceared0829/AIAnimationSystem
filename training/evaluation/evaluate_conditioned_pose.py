"""用每条测试动作的中心窗口，按既有非学习基线口径评估条件姿态模型。"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Subset

from training.pretrain.train_conditioned_pose import MotionWindows, ReferenceGuidedPose, verify_release


def center_indices(rows):
    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[row["clip_index"]].append(index)
    return [indices[len(indices) // 2] for _, indices in sorted(grouped.items())]


@torch.no_grad()
def evaluate(checkpoint_path, release, lock_path, baseline_path, output, source_override=None):
    contract, lock = verify_release(release, lock_path, source_override)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    config = checkpoint["config"]
    if config["contract_sha256"] != lock["artifacts_sha256"]["contract/contract.json"]:
        raise ValueError("检查点与封版数据不匹配")
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    if (baseline["contract_sha256"] != config["contract_sha256"]
            or baseline["split"] != "test"
            or baseline["selection"] != "middle_window_per_clip"
            or not baseline["oracle_root_condition"]):
        raise ValueError("非学习基线与封版测试集不匹配")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ReferenceGuidedPose(contract["bone_count"], config["width"]).to(device)
    model.load_state_dict(checkpoint["model"])
    model.eval()
    data = MotionWindows(release, contract, "test", seed=config["seed"])
    chosen = center_indices(data.rows)
    loader = DataLoader(Subset(data, chosen), batch_size=config["batch_size"], num_workers=0)
    std = torch.from_numpy(data.std).to(device)
    result = {}
    for scenario, baseline_key in (("no_refs", "no_reference/hold"),
                                   ("two_refs", "middle_and_end/linear_reference")):
        data.scenario = scenario
        errors = []
        for batch in loader:
            history, root, reference, mask, target = (part.to(device) for part in batch)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                predicted = model(history, root, reference, mask)
            predicted = predicted.float().reshape(len(history), 24, -1, 9)
            target = target.reshape(len(history), 24, -1, 9)
            squared_joint_cm = (((predicted[..., :3] - target[..., :3]) * std) ** 2).sum(-1) * 10000
            visible = (1 - mask).bool().expand_as(squared_joint_cm)
            for values, include in zip(squared_joint_cm, visible):
                errors.append(float(torch.sqrt(values[include].mean()).item()))
        result[scenario] = {"clips": len(errors), "non_anchor_pose_rmse_cm": float(np.mean(errors)),
                            "baseline_key": baseline_key,
                            "baseline_non_anchor_pose_rmse_cm": baseline["aggregate"][baseline_key]["non_anchor_pose_rmse_cm"]}
    report = {"checkpoint": str(Path(checkpoint_path).resolve()),
              "contract_sha256": config["contract_sha256"], "split": "test",
              "selection": "middle_window_per_clip", "oracle_root_condition": True,
              "metric": "mean_of_per_clip_non_anchor_joint_euclidean_rmse_cm", "scenarios": result,
              "limitations": ["原动作未来 Root 作为理想控制；不衡量实时 Root 规划。",
                              "模型旋转输出是 6D 数值，本报告只比较关节位置；蒙皮和接触未验收。"]}
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--lock", required=True)
    parser.add_argument("--source-override", help="跨系统迁移后的来源数据目录")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.checkpoint, args.release, args.lock, args.baseline, args.output,
                              args.source_override),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
