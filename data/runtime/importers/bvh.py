"""复用现有 BVH 解析与通道求值，保留局部变换及源时间轴。"""

import hashlib
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.bvh_reader import read_bvh
from data.runtime.native_motion import (
    NativeMotion,
    NativeSkeleton,
    NativeTrack,
    SourceInfo,
    SourceSpace,
    validate_native_motion,
)


def read_bvh_motion(path, source_profile: dict) -> NativeMotion:
    path = Path(path).resolve()
    bvh = read_bvh(path)
    times = np.arange(len(bvh.values)) * bvh.frame_time
    joints = len(bvh.names)
    rest_quats = np.tile([0., 0., 0., 1.], (joints, 1))
    skeleton = NativeSkeleton(bvh.names, np.asarray(bvh.parents, dtype=np.int64), bvh.offsets.copy(),
                              rest_quats, np.ones((joints, 3)))
    # 通道顺序会影响平移；由既有求值器计算，再严格逆回局部空间。
    positions, rotations = bvh.forward()
    local_p, local_r = positions.copy(), rotations.copy()
    for index, parent in enumerate(bvh.parents):
        if parent >= 0:
            inverse = rotations[:, parent].transpose(0, 2, 1)
            local_p[:, index] = np.einsum("tij,tj->ti", inverse, positions[:, index] - positions[:, parent])
            local_r[:, index] = inverse @ rotations[:, index]
    tracks = []
    absolute = set(source_profile.get("absolute_position_joints", []))
    if not absolute.issubset(bvh.names):
        raise ValueError("absolute_position_joints 包含不存在的关节")
    for index, channels in enumerate(bvh.channels):
        has_position = any(c.endswith("position") for c in channels)
        has_rotation = any(c.endswith("rotation") for c in channels)
        if bvh.names[index] in absolute:
            if not has_position:
                raise ValueError("绝对平移关节缺少 position 通道")
            local_p[:, index] -= bvh.offsets[index]
        tracks.append(NativeTrack(index, times.copy() if has_position else np.empty(0),
                                  local_p[:, index] if has_position else np.empty((0, 3)),
                                  times.copy() if has_rotation else np.empty(0),
                                  Rotation.from_matrix(local_r[:, index]).as_quat() if has_rotation else np.empty((0, 4)),
                                  np.empty(0), np.empty((0, 3))))
    # BVH 本身不可靠地声明单位/前向，必须由来源配置明确给出。
    space = SourceSpace(float(source_profile["meters_per_unit"]), np.asarray(source_profile["basis"], dtype=float))
    root_name = source_profile.get("root_joint")
    source = SourceInfo(source_profile.get("source_id", path.name), {str(path): hashlib.sha256(path.read_bytes()).hexdigest()},
                        "bvh_v1", {"profile": source_profile, "reference_policy": "bvh_offsets_zero_channels",
                                   "source_fps": 1 / bvh.frame_time})
    motion = NativeMotion(skeleton, tracks, float(times[-1]), space, source,
                          bvh.names.index(root_name) if root_name is not None else None)
    validate_native_motion(motion)
    return motion
