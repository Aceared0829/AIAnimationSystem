"""原生采样运动的正向运动学，不解释语义或接触。"""

import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.native_motion import SampledMotion


def world_positions(motion: SampledMotion):
    """复合局部 TRS，保留父级非均匀缩放产生的仿射变换。"""
    positions = motion.positions.copy()
    local = Rotation.from_quat(motion.rotations.reshape(-1, 4)).as_matrix().reshape(*motion.rotations.shape[:2], 3, 3)
    local = local * motion.scales[..., None, :]
    world = local.copy()
    for joint, parent in enumerate(motion.skeleton.parents):
        if parent >= 0:
            positions[:, joint] = positions[:, parent] + np.einsum("tij,tj->ti", world[:, parent], motion.positions[:, joint])
            world[:, joint] = world[:, parent] @ local[:, joint]
    return positions
