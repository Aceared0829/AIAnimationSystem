"""从已审核方向的动作建立站蹲过渡窗口，不改动原始 Root/姿态轨道。"""

import json
from collections import Counter
from pathlib import Path

import numpy as np

from data.runtime.conditioned_motion import load_raw, root_local, sha256
from motionbricks.data.unreal_dataset import contained_file, read_json


CONTRACT_ID = "stance_root_pose_v2"
STANCES = {"stand": 0, "crouch": 1}
TRANSITION = 2


def early_window_starts(length, history_frames=24, future_frames=24, stride_frames=4):
    """仅左侧历史可首帧补齐；所有未来帧必须来自原动作。"""
    if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0
           for value in (length, history_frames, future_frames, stride_frames)):
        raise ValueError("帧数和步长必须为正整数")
    if length <= future_frames:
        return []
    last = length - history_frames - future_frames
    # 起始窗口至少观察到源动作第 0 帧；未来从第 1 帧开始，避免把目标姿态作为补齐历史泄露。
    first = 1 - history_frames
    starts = list(range(first, last + 1, stride_frames))
    if starts[-1] != last:
        starts.append(last)
    return starts


def stance_labels(length, annotation):
    """将人工复核方向与暂定过渡区间展开为逐帧观察标签。"""
    start, end = annotation["transition_start"], annotation["transition_end"]
    if not 0 <= start <= end < length:
        raise ValueError("过渡区间越过真实帧边界")
    labels = np.full(length, STANCES[annotation["from_stance"]], dtype=np.int64)
    labels[start:end + 1] = TRANSITION
    labels[end + 1:] = STANCES[annotation["to_stance"]]
    return labels


def validate_annotations(base_contract, annotations):
    if annotations.get("schema_version") != 1 or annotations.get("base_contract_sha256") is None:
        raise ValueError("站蹲标注缺少版本或来源契约哈希")
    seen = set()
    validated = []
    for item in annotations.get("clips", []):
        index = item.get("clip_index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(base_contract["clips"]):
            raise ValueError("站蹲标注的片段索引无效")
        if index in seen:
            raise ValueError(f"片段 {index} 有重复站蹲标注")
        seen.add(index)
        clip = base_contract["clips"][index]
        if item.get("raw_sha256") != clip["raw_sha256"] or item.get("asset") != clip["asset"]:
            raise ValueError(f"片段 {index} 的资产或原始动作哈希不匹配")
        if item.get("from_stance") not in STANCES or item.get("to_stance") not in STANCES:
            raise ValueError("站蹲方向必须使用 stand/crouch")
        if item["from_stance"] == item["to_stance"]:
            raise ValueError("过渡的起点与终点状态相同")
        if item.get("status") not in ("provisional", "verified"):
            raise ValueError("标注必须声明 provisional 或 verified")
        if not item.get("evidence"):
            raise ValueError("标注缺少证据来源")
        stance_labels(clip["source_frames"], item)
        validated.append(item)
    if not validated:
        raise ValueError("没有可用的站蹲标注")
    return validated


def build_stance_index(base_folder, annotations_file, output, *, history_frames=24, future_frames=24,
                       stride_frames=4):
    """建立独立 v2 索引；保留 v1 的划分、Root 轨道和统计量。"""
    base_folder, annotations_file, output = Path(base_folder).resolve(), Path(annotations_file).resolve(), Path(output).resolve()
    base_path = base_folder / "contract.json"
    base = read_json(base_path)
    if base.get("contract_id") != "reference_guided_root_pose_v1":
        raise ValueError("来源必须是 reference_guided_root_pose_v1 条件契约")
    annotations = read_json(annotations_file)
    if annotations.get("base_contract_sha256") != sha256(base_path):
        raise ValueError("站蹲标注与来源契约哈希不匹配")
    selected = validate_annotations(base, annotations)
    if output.exists():
        raise FileExistsError(f"目标目录已存在：{output}")
    rows, counts, transition_counts = [], Counter(), Counter()
    for item in selected:
        clip = base["clips"][item["clip_index"]]
        starts = early_window_starts(clip["source_frames"], history_frames, future_frames, stride_frames)
        for start in starts:
            middle = start + history_frames
            is_transition = middle <= item["transition_end"] and middle + future_frames - 1 >= item["transition_start"]
            row = {"clip_index": item["clip_index"], "start": start, "future_contains_transition": is_transition}
            rows.append(row)
            counts[clip["split"]] += 1
            transition_counts[clip["split"]] += int(is_transition)
    contract = {"schema_version": 2, "contract_id": CONTRACT_ID,
                "base_contract": str(base_folder), "base_contract_sha256": sha256(base_path),
                "annotations_sha256": sha256(annotations_file), "source_dataset": base["source_dataset"],
                "source_manifest_sha256": base["source_manifest_sha256"], "skeleton_sha256": base["skeleton_sha256"],
                "fps": base["fps"], "bone_count": base["bone_count"],
                "window": {"history_frames": history_frames, "future_frames": future_frames,
                           "stride_frames": stride_frames, "history_first_frame_padding": True,
                           "future_padding": False},
                "root_condition_source": "ground_truth_oracle_for_offline_baseline_only",
                "stance_condition_source": "inferred_goal_from_annotated_source_animation_not_player_input",
                "accepted_stance_available": False, "can_uncrouch_available": False,
                "window_split_counts": dict(counts), "future_transition_window_split_counts": dict(transition_counts),
                "annotations": selected,
                "limitations": ["过渡边界与目标状态来自旧动画标注，不是玩家输入或 CMC 批准记录。",
                                "未来 Root 仍取原动作真值，不代表在线规划误差。",
                                "当前仅覆盖已显式标注的片段，不代表站蹲泛化。"]}
    output.mkdir(parents=True, exist_ok=False)
    with (output / "windows.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
    (output / "contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return contract


def load_stance_window(folder, row, *, contract=None, base_override=None, source_override=None):
    """返回离线可见条件与监督目标；不提供虚构的 CMC 执行状态。"""
    folder = Path(folder)
    contract = read_json(folder / "contract.json") if contract is None else contract
    if contract.get("contract_id") != CONTRACT_ID:
        raise ValueError("未知站蹲条件契约")
    base_folder = Path(base_override if base_override is not None else contract["base_contract"])
    base = read_json(base_folder / "contract.json")
    if sha256(base_folder / "contract.json") != contract["base_contract_sha256"]:
        raise ValueError("来源条件契约已改变")
    annotations = {item["clip_index"]: item for item in contract["annotations"]}
    index = row["clip_index"]
    if index not in annotations:
        raise ValueError("窗口片段没有站蹲标注")
    clip = base["clips"][index]
    source = Path(source_override if source_override is not None else contract["source_dataset"])
    raw, _ = load_raw(contained_file(source, clip["raw_file"]), clip["source_frames"], contract["bone_count"],
                      contract["fps"], expected_sha256=clip["raw_sha256"])
    history, future = contract["window"]["history_frames"], contract["window"]["future_frames"]
    start = row["start"]
    middle, end = start + history, start + history + future
    if not isinstance(start, int) or start < 1 - history or middle < 1 or end > clip["source_frames"]:
        raise ValueError("窗口越过历史补齐或未来真实帧边界")
    history_indices = np.arange(start, middle)
    padded_indices = np.maximum(history_indices, 0)
    origin = raw["root_track"][middle - 1]
    labels = stance_labels(clip["source_frames"], annotations[index])
    visible = {"history_pose": raw["positions"][padded_indices],
               "history_rotations": raw["rotations"][padded_indices],
               "history_root_local": root_local(raw["root_track"][padded_indices], origin),
               "history_valid_mask": history_indices >= 0,
               "future_root_plan_local": root_local(raw["root_track"][middle:end], origin),
               "goal_stance_proxy": np.full(future, STANCES[annotations[index]["to_stance"]], dtype=np.int64)}
    target = {"future_pose": raw["positions"][middle:end],
              "future_rotations": raw["rotations"][middle:end],
              "future_root_track": raw["root_track"][middle:end],
              "observed_stance": labels[middle:end]}
    return {"metadata": {"clip_index": index, "split": clip["split"], "asset": clip["asset"],
                         "start": start, "annotation_status": annotations[index]["status"]},
            "input": visible, "target": target}
