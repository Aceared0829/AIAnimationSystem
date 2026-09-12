"""逐片段读取 BVH，严格检查通道和帧数，并计算组件空间 FK。"""
from dataclasses import dataclass
from pathlib import Path
import re
import numpy as np
from scipy.spatial.transform import Rotation


@dataclass
class Bvh:
    names: list
    parents: list
    offsets: np.ndarray
    channels: list
    values: np.ndarray
    frame_time: float

    def forward(self, indices=None):
        values = self.values if indices is None else self.values[indices]
        positions = np.zeros((len(values), len(self.names), 3))
        rotations = np.zeros((len(values), len(self.names), 3, 3))
        cursor = 0
        for i, channels in enumerate(self.channels):
            translation = np.broadcast_to(self.offsets[i], (len(values), 3)).copy()
            local = np.broadcast_to(np.eye(3), (len(values), 3, 3)).copy()
            # 按 BVH 声明顺序右乘局部变换，支持 Hips 的额外平移通道。
            for channel in channels:
                axis = 'XYZ'.index(channel[0])
                if channel.endswith('position'):
                    delta = np.zeros((len(values), 3))
                    delta[:, axis] = values[:, cursor]
                    translation += np.einsum('tij,tj->ti', local, delta)
                else:
                    rotvec = np.zeros((len(values), 3))
                    rotvec[:, axis] = np.deg2rad(values[:, cursor])
                    local = local @ Rotation.from_rotvec(rotvec).as_matrix()
                cursor += 1
            parent = self.parents[i]
            if parent < 0:
                positions[:, i] = translation
                rotations[:, i] = local
            else:
                positions[:, i] = positions[:, parent] + np.einsum('tij,tj->ti', rotations[:, parent], translation)
                rotations[:, i] = rotations[:, parent] @ local
        return positions, rotations


def read_bvh(path):
    path = Path(path)
    if path.stat().st_size > 256 * 1024**2:
        raise ValueError('单片段超过 256 MiB，需单独处理')
    text = path.read_text(encoding='utf-8-sig')
    hierarchy, motion = text.split('MOTION', 1)
    tokens = iter(re.findall(r'[^\s{}]+|[{}]', hierarchy))
    if next(tokens) != 'HIERARCHY':
        raise ValueError('缺少 HIERARCHY')
    names, parents, offsets, channels = [], [], [], []

    def joint(kind, parent):
        if kind == 'End':
            assert next(tokens) == 'Site'
            assert next(tokens) == '{'
            assert next(tokens) == 'OFFSET'
            for _ in range(3):
                float(next(tokens))
            assert next(tokens) == '}'
            return
        if kind not in ('ROOT', 'JOINT'):
            raise ValueError(f'未知骨骼标记 {kind}')
        name = next(tokens)
        if name in names:
            raise ValueError(f'重复骨骼 {name}')
        i = len(names)
        names.append(name)
        parents.append(parent)
        assert next(tokens) == '{'
        assert next(tokens) == 'OFFSET'
        offsets.append([float(next(tokens)) for _ in range(3)])
        assert next(tokens) == 'CHANNELS'
        count = int(next(tokens))
        if not 0 <= count <= 6:
            raise ValueError('非法通道数')
        ch = [next(tokens) for _ in range(count)]
        if len(set(ch)) != count or any(c not in [a+s for a in 'XYZ' for s in ('position','rotation')] for c in ch):
            raise ValueError('非法通道名称')
        channels.append(ch)
        while True:
            token = next(tokens)
            if token == '}':
                return
            joint(token, i)

    joint(next(tokens), -1)
    if list(tokens):
        raise ValueError('骨架存在未解析内容')
    match = re.fullmatch(r'\s*Frames:\s*(\d+)\s*Frame Time:\s*([\d.eE+-]+)\s*(.*)', motion, re.S)
    if not match:
        raise ValueError('无效 MOTION 头')
    count, frame_time = int(match[1]), float(match[2])
    if count < 1 or not np.isfinite(frame_time) or frame_time <= 0:
        raise ValueError('无效帧数或帧间隔')
    values = np.fromstring(match[3], sep=' ')
    if values.size != count * sum(map(len, channels)) or not np.isfinite(values).all():
        raise ValueError('运动数据帧数/通道数不匹配或包含非有限数值')
    return Bvh(names, parents, np.asarray(offsets), channels, values.reshape(count, -1), frame_time)
