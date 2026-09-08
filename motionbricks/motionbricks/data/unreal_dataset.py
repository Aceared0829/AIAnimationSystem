"""Unreal 导出协议、参考姿态转换及真实动画训练集。"""

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import torch
from scipy.spatial.transform import Rotation
from torch.utils.data import Dataset

from motionbricks.motionlib.core.skeletons.base import SkeletonBase


# UE X 前、Y 右、Z 上 → 动作空间 Z 前、X 左、Y 上；同时改变手性。
UE_TO_MOTION = np.array([[0, -1, 0], [0, 0, 1], [1, 0, 0]], dtype=np.float64)
ROLE_KEYS = ("right_hip", "left_hip", "left_foot", "left_toe", "right_foot", "right_toe")


def derive_motion_labels(asset, source_frames=None):
    """从 UEFN 动画资产路径生成稳定、可审阅的动作语义标签。

    这些字段保存在数据集清单中，既便于按动作类型检索，也为后续把文本嵌入接入
    Pose/Root Transformer 留出一对一的中文和英文提示词来源。它们不是由模型猜出的标注。
    """
    asset = str(asset)
    path_parts = [part for part in asset.split("/") if part]
    asset_name = path_parts[-1].split(".", 1)[0] if path_parts else asset
    # UE 导出资产通常是 Package.Asset；语义可能出现在任意一侧，因此整个路径参与解析。
    tokens = asset.lower().replace("-", "_")
    name_tokens = set(re.split(r"[^a-z0-9]+", asset_name.lower()))
    category = "其他"
    if "animations" in [part.lower() for part in path_parts]:
        animation_index = next(index for index, part in enumerate(path_parts) if part.lower() == "animations")
        if animation_index + 1 < len(path_parts) - 1:
            category = path_parts[animation_index + 1]

    action_rules = (
        ("aim_offset", ("aimoffset", "_ao_"), "瞄准偏移", "aim offset"),
        ("crouch", ("crouch",), "下蹲", "crouch"),
        ("jump", ("jump",), "跳跃", "jump"),
        ("sprint", ("sprint",), "冲刺", "sprint"),
        ("run", ("run",), "跑步", "run"),
        ("walk", ("walk",), "行走", "walk"),
        ("slide", ("slide",), "滑铲", "slide"),
        ("climb", ("climb",), "攀爬", "climb"),
        ("mantle", ("mantle",), "翻越上攀", "mantle"),
        ("vault", ("vault",), "翻越", "vault"),
        ("hurdle", ("hurdle",), "跨栏", "hurdle"),
        ("tackle", ("tackle",), "擒抱", "tackle"),
        ("takedown", ("takedown",), "制服", "takedown"),
        ("catch", ("catch",), "接取", "catch"),
        ("ragdoll", ("ragdoll",), "布娃娃", "ragdoll"),
        ("idle", ("idle", "stand"), "待机", "idle"),
        ("pose", ("pose",), "姿势", "pose"),
    )
    action_id, action_zh, action_en = "other", "其他动作", "other motion"
    category_action = {"aimoffset": "aim_offset", "crouch": "crouch", "idle": "idle", "jump": "jump", "poses": "pose",
                       "run": "run", "slide": "slide", "sprint": "sprint", "walk": "walk"}.get(category.lower())
    if category.lower() == "traversal":
        category_action = next((action for action in ("climb", "mantle", "vault", "hurdle", "catch") if action in asset_name.lower()), None)
    for candidate_id, patterns, candidate_zh, candidate_en in action_rules:
        if candidate_id == category_action or (category_action is None and any(pattern in tokens or pattern in category.lower() for pattern in patterns)):
            action_id, action_zh, action_en = candidate_id, candidate_zh, candidate_en
            break

    style_id, style_zh, style_en = "unknown", "未注明风格", "unspecified style"
    if "neutral" in tokens:
        style_id, style_zh, style_en = "neutral", "中性", "neutral"
    elif "relaxed" in tokens:
        style_id, style_zh, style_en = "relaxed", "放松", "relaxed"

    phase_rules = (
        ("start", "起步", "start"), ("stop", "停止", "stop"), ("loop", "循环", "loop"),
        ("pivot", "急转", "pivot"), ("turn", "转向", "turn"), ("spin", "旋转", "spin"),
        ("land", "落地", "land"), ("off", "起跳", "takeoff"), ("reface", "重定向", "reface"),
        ("into", "进入", "enter"), ("out", "退出", "exit"), ("end", "结束", "end"),
    )
    phase_id, phase_zh, phase_en = "full", "完整动作", "full motion"
    for candidate_id, candidate_zh, candidate_en in phase_rules:
        if candidate_id in name_tokens:
            phase_id, phase_zh, phase_en = candidate_id, candidate_zh, candidate_en
            break

    direction_rules = (("forward", ("_f_", "_fwd", "forward"), "前"), ("backward", ("_b_", "_bwd", "backward"), "后"),
                       ("left", ("_l_", "_ll", "left"), "左"), ("right", ("_r_", "_rr", "right"), "右"))
    aliases = {"forward": {"f", "fwd", "forward", "fl", "fr"}, "backward": {"b", "bwd", "backward", "bl", "br"},
               "left": {"l", "ll", "left", "fl", "bl"}, "right": {"r", "rr", "right", "fr", "br"}}
    directions = [candidate for candidate, _, _ in direction_rules if name_tokens & aliases[candidate]]
    direction_id = "_and_".join(directions) if directions else "unspecified"
    direction_zh = "、".join(next(zh for candidate, _, zh in direction_rules if candidate == direction) for direction in directions) if directions else "未指定方向"
    direction_en = " and ".join(directions) if directions else "unspecified direction"

    tags = [f"action:{action_id}", f"style:{style_id}", f"phase:{phase_id}", f"direction:{direction_id}", f"category:{category.lower()}"]
    if source_frames is not None and source_frames < 65:
        tags.append("role:pose_anchor")
    style_prefix_zh = "" if style_id == "unknown" else f"{style_zh}风格的"
    style_prefix_en = "" if style_id == "unknown" else f"{style_en} "
    phase_suffix_zh = "" if phase_id == "full" else phase_zh
    phase_suffix_en = "" if phase_id == "full" else f" {phase_en}"
    description_zh = f"{style_prefix_zh}{action_zh}{phase_suffix_zh}动作"
    description_en = f"{style_prefix_en}{action_en}{phase_suffix_en} motion"
    if direction_id != "unspecified":
        description_zh += f"，方向为{direction_zh}。"
        description_en += f", moving {direction_en}."
    else:
        description_zh += "。"
        description_en += "."
    if source_frames is not None and source_frames < 65:
        description_zh += " 原始片段较短，作为姿势锚点保持末帧补齐。"
        description_en += " Short source clip; end-held as a pose anchor."
    return {"schema_version": 1, "category": category, "action": action_id, "style": style_id, "phase": phase_id,
            "direction": direction_id, "tags": tags, "description_zh": description_zh, "prompt_en": description_en,
            "asset_name": asset_name}


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def contained_file(folder, filename):
    folder = Path(folder).resolve()
    result = (folder / filename).resolve()
    if not result.is_relative_to(folder) or not result.is_file():
        raise ValueError(f"数据文件不存在或越过数据目录：{filename}")
    return result


def skeleton_signature(metadata):
    fields = {key: metadata[key] for key in ("roles", "coordinate_system", "fps")}
    fields["bones"] = training_bones(metadata["bones"])
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def training_bones(bones):
    """移除 Unreal 虚拟骨骼，并把保留骨骼重新接回最近的实体祖先。"""
    retained = [index for index, bone in enumerate(bones) if not bone["name"].startswith("VB ")]
    index_map = {old_index: new_index for new_index, old_index in enumerate(retained)}
    result = []
    for old_index in retained:
        bone = dict(bones[old_index])
        parent = bone["parent"]
        while parent != -1 and parent not in index_map:
            parent = bones[parent]["parent"]
        bone["parent"] = -1 if parent == -1 else index_map[parent]
        result.append(bone)
    return result


def training_signature(folder):
    """绑定参考骨架与归一化统计量，避免同拓扑但不同统计量的权重被误用。"""
    folder = Path(folder)
    digest = hashlib.sha256()
    for name in ("skeleton.json", "stats/mean.npy", "stats/std.npy"):
        digest.update((folder / name).read_bytes())
    return digest.hexdigest()


def validate_clip(clip):
    if clip.get("schema_version") != 1 or clip.get("coordinate_system") != "unreal_component_cm_xyzw":
        raise ValueError("不支持的 Unreal 动画导出协议")
    fps = clip.get("fps")
    if not isinstance(fps, (int, float)) or not np.isfinite(fps) or not 1 <= fps <= 120:
        raise ValueError("fps 必须处于 1–120")
    bones = clip["bones"]
    names = [bone["name"] for bone in bones]
    if not 3 <= len(names) <= 512 or len(set(names)) != len(names):
        raise ValueError("骨骼名称必须唯一，数量须在 3–512 之间")
    for index, bone in enumerate(bones):
        parent = bone["parent"]
        if not isinstance(parent, int) or (index == 0 and parent != -1) or (index > 0 and not 0 <= parent < index):
            raise ValueError("骨骼必须按父先子后排序，并仅含一个身体根节点")
    roles = clip["roles"]
    if any(roles.get(key) not in names for key in ROLE_KEYS):
        raise ValueError("髋、脚踝和脚掌角色必须映射到已导出的骨骼")
    if len({roles[key] for key in ROLE_KEYS}) != len(ROLE_KEYS):
        raise ValueError("髋与四个接触点必须分别对应不同骨骼")
    frames = np.asarray(clip["frames"], dtype=np.float64)
    if frames.ndim != 3 or frames.shape[1:] != (len(names), 7) or not 2 <= len(frames) <= 18000:
        raise ValueError("frames 必须是 [2..18000, 骨骼数, 7] 的位置与 xyzw 四元数")
    ref_pos = np.asarray([bone["position"] for bone in bones], dtype=np.float64)
    ref_quat = np.asarray([bone["rotation"] for bone in bones], dtype=np.float64)
    if ref_pos.shape != (len(names), 3) or ref_quat.shape != (len(names), 4):
        raise ValueError("参考姿态维数错误")
    for values in (frames, ref_pos, ref_quat):
        if not np.isfinite(values).all():
            raise ValueError("动画包含 NaN 或 Infinity")
    for quats in (frames[..., 3:], ref_quat):
        if not np.allclose(np.linalg.norm(quats, axis=-1), 1, atol=1e-3):
            raise ValueError("动画包含非单位四元数")
    return frames, ref_pos, ref_quat


def convert_clip(clip):
    """返回米制位置、消除参考骨轴后的全局旋转和根节点归零的参考关节。"""
    frames, ref_pos, ref_quat = validate_clip(clip)
    source_bones = clip["bones"]
    retained = [index for index, bone in enumerate(source_bones) if not bone["name"].startswith("VB ")]
    frames, ref_pos, ref_quat = frames[:, retained], ref_pos[retained], ref_quat[retained]
    positions = frames[..., :3] @ UE_TO_MOTION.T * 0.01
    neutral = (ref_pos - ref_pos[:1]) @ UE_TO_MOTION.T * 0.01
    rotations = Rotation.from_quat(frames[..., 3:].reshape(-1, 4)).as_matrix().reshape(*frames.shape[:2], 3, 3)
    reference = Rotation.from_quat(ref_quat).as_matrix()
    # UE 骨轴包含参考姿态旋转；MotionBricks FK 以参考关节位置和单位局部旋转为基准。
    rotations = UE_TO_MOTION @ (rotations @ reference.transpose(0, 2, 1)) @ UE_TO_MOTION.T
    roles = clip["roles"]
    names = [bone["name"] for bone in training_bones(source_bones)]
    across = positions[:, names.index(roles["right_hip"])] - positions[:, names.index(roles["left_hip"])]
    if np.any(np.linalg.norm(across[:, [0, 2]], axis=-1) < 1e-5):
        raise ValueError("左右髋的水平间距退化，无法计算朝向")
    return positions.astype(np.float32), rotations.astype(np.float32), neutral.astype(np.float32)


class UnrealSkeleton(SkeletonBase):
    """从数据集的 skeleton.json 建立骨架；只允许同一拓扑内的表示转换。"""

    name = "unreal"

    def __init__(self, folder):
        metadata = read_json(Path(folder) / "skeleton.json")
        bones, roles = metadata["bones"], metadata["roles"]
        self.bone_order_names_with_parents = [(bone["name"], None if bone["parent"] == -1 else bones[bone["parent"]]["name"]) for bone in bones]
        self.hip_joint_names = [roles["right_hip"], roles["left_hip"]]
        self.left_foot_joint_names = [roles["left_foot"], roles["left_toe"]]
        self.right_foot_joint_names = [roles["right_foot"], roles["right_toe"]]
        super().__init__(folder=str(folder), load=False, t_pose="unreal_reference")
        self.register_buffer("neutral_joints", torch.tensor(metadata["neutral_joints"], dtype=torch.float32), persistent=False)

    def get_skel_slice(self, skeleton):
        if skeleton.bone_order_names_with_parents != self.bone_order_names_with_parents:
            raise ValueError("骨架拓扑不匹配；此加载器不执行重定向")
        return list(range(self.nbjoints))


class UnrealMotionDataset(Dataset):
    """读取预处理完成的归一化全局动作；拒绝不满足训练窗口长度的数据。"""

    def __init__(self, folder, min_frames=65):
        self.folder = Path(folder).resolve()
        self.manifest = read_json(self.folder / "dataset.json")
        if self.manifest.get("schema_version") != 1:
            raise ValueError("不支持的数据集版本")
        if self.manifest.get("training_signature") != training_signature(self.folder):
            raise ValueError("骨架或统计量已改变，请重新预处理数据集")
        skeleton = read_json(self.folder / "skeleton.json")
        if self.manifest["fps"] != skeleton["fps"] or self.manifest["feature_dim"] != 12 * len(skeleton["bones"]) + 6:
            raise ValueError("清单帧率或特征维数与骨架不匹配")
        self.files = []
        for item in self.manifest["clips"]:
            path = contained_file(self.folder, item["file"])
            motion = np.load(path, mmap_mode="r", allow_pickle=False)
            if motion.ndim != 2 or motion.shape[1] != self.manifest["feature_dim"] or len(motion) < min_frames:
                raise ValueError(f"{path.name} 维数错误或少于 {min_frames} 帧，请提供更长片段")
            if not np.isfinite(motion).all():
                raise ValueError(f"{path.name} 包含无效特征")
            self.files.append(path)
        if not self.files:
            raise ValueError("训练集为空")

    def __len__(self):
        return len(self.files)

    def __getitem__(self, index):
        item = self.manifest["clips"][index]
        return {"keyid": index, "motion": torch.from_numpy(np.load(self.files[index], allow_pickle=False).copy()),
                "valid_frames": item.get("source_frames", item["frames"]),
                "labels": item.get("labels")}
