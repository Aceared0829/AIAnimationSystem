"""读取固定参考骨架；不解释运动 Root，也不决定采样时间轴。"""

import json
from pathlib import Path

import numpy as np

from data.runtime.native_motion import NativeSkeleton, validate_skeleton
from data.runtime.native_motion_io import skeleton_signature


def load_skeleton_contract(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if (document.get("schema"), document.get("version")) != ("motionweaver_skeleton", 1):
        raise ValueError("不支持的固定骨架契约")
    if document["coordinate_system"] != "motion_m_y_up_z_forward_xyzw":
        raise ValueError("固定骨架必须使用米制 Motion 坐标")
    fields = document["skeleton"]
    skeleton = NativeSkeleton(fields["names"], np.asarray(fields["parents"], dtype=np.int64),
                              np.asarray(fields["rest_positions"], dtype=np.float64),
                              np.asarray(fields["rest_rotations"], dtype=np.float64),
                              np.asarray(fields["rest_scales"], dtype=np.float64))
    validate_skeleton(skeleton)
    if skeleton_signature(skeleton) != document["skeleton_signature"]:
        raise ValueError("固定骨架内容与签名不一致")
    if any(name not in skeleton.names for name in document["roles"].values()):
        raise ValueError("骨架语义角色引用了不存在的节点")
    return skeleton, document
