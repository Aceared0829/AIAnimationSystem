"""将原生局部运动转换到 Motion 空间并显式重采样；不执行重定向或 Root 推导。"""

from dataclasses import replace

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from data.runtime.native_motion import (
    NativeMotion,
    NativeSkeleton,
    SampledMotion,
    SourceSpace,
    validate_native_motion,
    validate_sampled_motion,
)


def convert_space(motion: NativeMotion) -> NativeMotion:
    validate_native_motion(motion)
    basis, units = motion.space.basis, motion.space.meters_per_unit

    def positions(values):
        return values @ basis.T * units

    def rotations(values):
        if not len(values):
            return values.copy()
        matrices = Rotation.from_quat(values).as_matrix()
        return Rotation.from_matrix(basis @ matrices @ basis.T).as_quat()

    def scales(values):
        return values @ np.abs(basis).T

    skeleton = motion.skeleton
    converted = NativeSkeleton(skeleton.names.copy(), skeleton.parents.copy(), positions(skeleton.rest_positions),
                               rotations(skeleton.rest_rotations), scales(skeleton.rest_scales))
    tracks = [replace(t, positions=positions(t.positions), rotations=rotations(t.rotations), scales=scales(t.scales))
              for t in motion.tracks]
    return replace(motion, skeleton=converted, tracks=tracks, space=SourceSpace(1.0, np.eye(3)))


def sample_motion(motion: NativeMotion, fps: float) -> SampledMotion:
    validate_native_motion(motion)
    if motion.additive != "none":
        raise ValueError("Additive 动画尚未组合基准姿态，不能作为绝对运动标准化")
    if motion.space.meters_per_unit != 1 or not np.array_equal(motion.space.basis, np.eye(3)):
        raise ValueError("采样前必须转换到 Motion 空间")
    if not np.isfinite(fps) or not 1 <= fps <= 240:
        raise ValueError("目标 FPS 必须在 1–240 之间")
    # 保持固定采样间隔，不拉伸时间或额外制造一个超过原始时长的末帧。
    timestamps = np.arange(int(np.floor((motion.duration + 1e-6) * fps)) + 1) / fps
    skeleton = motion.skeleton
    positions = np.broadcast_to(skeleton.rest_positions, (len(timestamps), *skeleton.rest_positions.shape)).copy()
    rotations = np.broadcast_to(skeleton.rest_rotations, (len(timestamps), *skeleton.rest_rotations.shape)).copy()
    scales = np.broadcast_to(skeleton.rest_scales, (len(timestamps), *skeleton.rest_scales.shape)).copy()
    mask = np.zeros((len(skeleton.names), 3), dtype=bool)
    for track in motion.tracks:
        channels = ((track.position_times, track.positions, track.position_interpolation, positions),
                    (track.rotation_times, track.rotations, track.rotation_interpolation, rotations),
                    (track.scale_times, track.scales, track.scale_interpolation, scales))
        for channel, (times, values, interpolation, destination) in enumerate(channels):
            if not len(times):
                continue
            mask[track.joint_index, channel] = True
            query = np.clip(timestamps, times[0], times[-1])
            if interpolation == "STEP" or len(times) == 1:
                sampled = values[np.searchsorted(times, query, side="right") - 1]
            elif channel == 1:
                sampled = Slerp(times, Rotation.from_quat(values))(query).as_quat()
            else:
                sampled = np.column_stack([np.interp(query, times, values[:, axis]) for axis in range(3)])
            destination[:, track.joint_index] = sampled
    source = replace(motion.source, details=dict(motion.source.details, normalization={"version": "normalize_v1", "fps": fps,
                     "endpoint_tolerance_seconds": 1e-6, "missing_channels": "reference_transform",
                     "rotation_interpolation": "slerp", "space": "motion_m_y_up_xyzw"}))
    result = SampledMotion(skeleton, timestamps, positions, rotations, scales, mask, source,
                           motion.duration, fps, motion.root_joint)
    validate_sampled_motion(result)
    return result


def normalize_motion(motion: NativeMotion, fps: float = 30) -> SampledMotion:
    return sample_motion(convert_space(motion), fps)
