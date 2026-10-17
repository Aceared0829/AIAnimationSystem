"""独立运动契约：原生局部轨道与统一采样结果，不依赖 UE 或训练模块。"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SourceSpace:
    """basis 将来源向量转换为右手 Motion 空间（米、Y 上、Z 前）。"""

    meters_per_unit: float
    basis: np.ndarray


@dataclass
class SourceInfo:
    source_id: str
    file_hashes: dict[str, str]
    importer: str
    details: dict = field(default_factory=dict)


@dataclass
class NativeSkeleton:
    names: list[str]
    parents: np.ndarray
    rest_positions: np.ndarray
    rest_rotations: np.ndarray
    rest_scales: np.ndarray


@dataclass
class NativeTrack:
    joint_index: int
    position_times: np.ndarray
    positions: np.ndarray
    rotation_times: np.ndarray
    rotations: np.ndarray
    scale_times: np.ndarray
    scales: np.ndarray
    position_interpolation: str = "LINEAR"
    rotation_interpolation: str = "LINEAR"
    scale_interpolation: str = "LINEAR"


@dataclass
class NativeMotion:
    skeleton: NativeSkeleton
    tracks: list[NativeTrack]
    duration: float
    space: SourceSpace
    source: SourceInfo
    root_joint: int | None = None
    additive: str = "none"


@dataclass
class SampledMotion:
    skeleton: NativeSkeleton
    timestamps: np.ndarray
    positions: np.ndarray
    rotations: np.ndarray
    scales: np.ndarray
    track_mask: np.ndarray
    source: SourceInfo
    source_duration: float
    fps: float
    root_joint: int | None = None


def validate_skeleton(skeleton: NativeSkeleton) -> None:
    count = len(skeleton.names)
    if not count or len(set(skeleton.names)) != count or any(not name for name in skeleton.names):
        raise ValueError("骨骼名称必须非空且唯一")
    if skeleton.parents.shape != (count,) or skeleton.parents.dtype.kind not in "iu":
        raise ValueError("父索引必须是 [J] 整数数组")
    for index, parent in enumerate(skeleton.parents):
        if parent < -1 or parent >= index:
            raise ValueError("骨架必须按父先子后排序，根节点父索引为 -1")
    for values, width in ((skeleton.rest_positions, 3), (skeleton.rest_rotations, 4), (skeleton.rest_scales, 3)):
        if values.shape != (count, width) or not np.isfinite(values).all():
            raise ValueError("参考局部变换维数错误或包含非有限值")
    validate_quaternions(skeleton.rest_rotations)
    if np.any(skeleton.rest_scales <= 0):
        raise ValueError("首版不支持零或负参考缩放")


def validate_quaternions(values: np.ndarray) -> None:
    if not np.allclose(np.linalg.norm(values, axis=-1), 1, atol=1e-3):
        raise ValueError("旋转必须是单位 xyzw 四元数")


def validate_native_motion(motion: NativeMotion) -> None:
    validate_skeleton(motion.skeleton)
    if not np.isfinite(motion.duration) or motion.duration < 0:
        raise ValueError("时长必须是非负有限秒数")
    basis = motion.space.basis
    if (basis.shape != (3, 3) or not np.isfinite(basis).all()
            or not np.allclose(basis @ basis.T, np.eye(3), atol=1e-8)
            or not np.allclose(np.abs(basis), np.round(np.abs(basis)), atol=1e-8)):
        raise ValueError("来源轴基必须是正交的带符号轴置换矩阵")
    if not np.isfinite(motion.space.meters_per_unit) or motion.space.meters_per_unit <= 0:
        raise ValueError("来源单位必须明确为正的 meters_per_unit")
    if motion.root_joint is not None and not 0 <= motion.root_joint < len(motion.skeleton.names):
        raise ValueError("Root 索引越界")
    seen = set()
    for track in motion.tracks:
        if track.joint_index in seen or not 0 <= track.joint_index < len(motion.skeleton.names):
            raise ValueError("动画轨道骨骼索引重复或越界")
        seen.add(track.joint_index)
        for channel, width in (("position", 3), ("rotation", 4), ("scale", 3)):
            times = getattr(track, channel + "_times")
            values = getattr(track, {"position": "positions", "rotation": "rotations", "scale": "scales"}[channel])
            if times.ndim != 1 or values.shape != (len(times), width):
                raise ValueError(f"{channel} 关键帧时间与数值维数不匹配")
            if not np.isfinite(times).all() or not np.isfinite(values).all():
                raise ValueError("轨道包含非有限值")
            if len(times) and (times[0] < 0 or times[-1] > motion.duration + 1e-6 or np.any(np.diff(times) <= 0)):
                raise ValueError("轨道时间必须严格递增且位于片段范围内")
            if getattr(track, channel + "_interpolation") not in ("LINEAR", "STEP"):
                raise ValueError("首版只支持 LINEAR 与 STEP 轨道")
            if channel == "rotation":
                validate_quaternions(values)
            if channel == "scale" and np.any(values <= 0):
                raise ValueError("首版不支持零或负动画缩放")
    if not any(len(t.positions) + len(t.rotations) + len(t.scales) for t in motion.tracks):
        raise ValueError("动画缺少可用变换轨道")


def validate_sampled_motion(motion: SampledMotion) -> None:
    validate_skeleton(motion.skeleton)
    count, joints = len(motion.timestamps), len(motion.skeleton.names)
    if (not count or not np.isfinite(motion.timestamps).all() or motion.timestamps[0] != 0
            or not np.isfinite(motion.fps) or motion.fps <= 0
            or not np.isfinite(motion.source_duration) or motion.source_duration < 0
            or motion.timestamps[-1] > motion.source_duration + 1e-6
            or not np.allclose(np.diff(motion.timestamps), 1 / motion.fps, atol=1e-8)):
        raise ValueError("标准化时间轴不符合固定 FPS 契约")
    for values, width in ((motion.positions, 3), (motion.rotations, 4), (motion.scales, 3)):
        if values.shape != (count, joints, width) or not np.isfinite(values).all():
            raise ValueError("标准化轨道维数错误或包含非有限值")
    validate_quaternions(motion.rotations)
    if np.any(motion.scales <= 0):
        raise ValueError("标准化缩放必须为正")
    if motion.track_mask.shape != (joints, 3) or motion.track_mask.dtype != np.bool_:
        raise ValueError("track_mask 必须是 [J,3] 布尔数组")
    if motion.root_joint is not None and not 0 <= motion.root_joint < joints:
        raise ValueError("标准化 Root 索引越界")
