"""读取 glTF 2.0/GLB 的骨架节点与 LINEAR/STEP 动画，保留祖先节点变换。"""

import base64
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.native_motion import (
    NativeMotion,
    NativeSkeleton,
    NativeTrack,
    SourceInfo,
    SourceSpace,
    validate_native_motion,
)


def read_gltf_motion(path, animation_id: int, skin_index: int = 0) -> NativeMotion:
    path = Path(path).resolve()
    raw = path.read_bytes()
    hashes = {str(path): hashlib.sha256(raw).hexdigest()}
    binary = None
    if path.suffix.lower() == ".glb":
        if len(raw) < 12 or struct.unpack_from("<III", raw) != (0x46546C67, 2, len(raw)):
            raise ValueError("无效 GLB 2.0 头")
        offset, chunks = 12, {}
        while offset < len(raw):
            if len(raw) - offset < 8:
                raise ValueError("GLB 块头截断")
            length, kind = struct.unpack_from("<II", raw, offset)
            offset += 8
            if offset + length > len(raw) or kind in chunks:
                raise ValueError("GLB 块截断或重复")
            chunks[kind] = raw[offset:offset + length]
            offset += length
        document = json.loads(chunks[0x4E4F534A])
        binary = chunks.get(0x004E4942)
    else:
        document = json.loads(raw)
    if document["asset"]["version"] != "2.0" or document.get("extensionsRequired"):
        raise ValueError("仅支持无必需扩展的 glTF 2.0")
    if not 0 <= animation_id < len(document.get("animations", [])):
        raise ValueError("glTF animation_id 越界")
    if not 0 <= skin_index < len(document.get("skins", [])):
        raise ValueError("glTF skin_index 越界")
    buffers = []
    for item in document["buffers"]:
        uri = item.get("uri")
        if uri is None:
            if binary is None:
                raise ValueError("缺少 GLB 二进制块")
            data = binary
        elif uri.startswith("data:"):
            header, encoded = uri.split(",", 1)
            if not header.endswith(";base64"):
                raise ValueError("只支持 base64 data URI")
            data = base64.b64decode(encoded, validate=True)
        else:
            dependency = (path.parent / unquote(uri)).resolve()
            if not dependency.is_relative_to(path.parent):
                raise ValueError("glTF buffer 路径越界")
            data = dependency.read_bytes()
            hashes[str(dependency)] = hashlib.sha256(data).hexdigest()
        if len(data) < item["byteLength"]:
            raise ValueError("glTF buffer 截断")
        buffers.append(data)

    def accessor(index):
        item = document["accessors"][index]
        if item.get("sparse") or item.get("normalized") or item["componentType"] != 5126:
            raise ValueError("动画 accessor 必须是非 sparse、非 normalized 的 float32")
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}[item["type"]]
        view = document["bufferViews"][item["bufferView"]]
        offset = item.get("byteOffset", 0)
        stride = view.get("byteStride", 4 * width)
        count = item["count"]
        if count < 1 or offset < 0 or stride < 4 * width or offset + (count - 1) * stride + 4 * width > view["byteLength"]:
            raise ValueError("动画 accessor 越过 bufferView")
        start = view.get("byteOffset", 0) + offset
        data = buffers[view["buffer"]]
        if start < 0 or start + (count - 1) * stride + 4 * width > len(data):
            raise ValueError("动画 accessor 越过 buffer")
        return np.ndarray((count, width), dtype="<f4", buffer=data, offset=start, strides=(stride, 4)).astype(float)

    nodes = document["nodes"]
    parents = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            if child in parents or not 0 <= child < len(nodes):
                raise ValueError("节点具有多个父节点或索引越界")
            parents[child] = index
    selected = set(document["skins"][skin_index]["joints"])
    for joint in list(selected):
        visited = set()
        while joint in parents:
            if joint in visited:
                raise ValueError("骨架祖先存在循环")
            visited.add(joint)
            joint = parents[joint]
            selected.add(joint)
    order = []

    def add(index):
        if index in order:
            return
        if index in parents:
            add(parents[index])
        order.append(index)

    for index in sorted(selected):
        add(index)
    index_map = {node: index for index, node in enumerate(order)}
    original_names = [nodes[index].get("name", f"node_{index}") for index in order]
    counts = Counter(original_names)
    names = [name if counts[name] == 1 else f"{name}#node_{index}" for name, index in zip(original_names, order)]
    rest_p, rest_r, rest_s = [], [], []
    for index in order:
        node = nodes[index]
        if "matrix" in node:
            matrix = np.asarray(node["matrix"], dtype=float).reshape(4, 4).T
            scale = np.linalg.norm(matrix[:3, :3], axis=0)
            rotation = matrix[:3, :3] / scale
            if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6) or np.linalg.det(rotation) < 0:
                raise ValueError("节点矩阵包含 shear 或反射，首版不支持")
            if not np.allclose(matrix[3], [0, 0, 0, 1]):
                raise ValueError("无效节点仿射矩阵")
            p, r, s = matrix[:3, 3], Rotation.from_matrix(rotation).as_quat(), scale
        else:
            p, r, s = node.get("translation", [0, 0, 0]), node.get("rotation", [0, 0, 0, 1]), node.get("scale", [1, 1, 1])
        rest_p.append(p); rest_r.append(r); rest_s.append(s)
    skeleton = NativeSkeleton(names, np.asarray([index_map[parents[i]] if i in parents else -1 for i in order], dtype=np.int64),
                              np.asarray(rest_p, dtype=float), np.asarray(rest_r, dtype=float), np.asarray(rest_s, dtype=float))
    animation = document["animations"][animation_id]
    track_fields, duration = {}, 0.0
    ignored_nodes = set()
    for channel in animation["channels"]:
        sampler = animation["samplers"][channel["sampler"]]
        times = accessor(sampler["input"])[:, 0]
        duration = max(duration, float(times[-1]))
        target = channel["target"]
        node_index = target["node"]
        if node_index not in index_map:
            ignored_nodes.add(node_index)
            continue
        if "matrix" in nodes[node_index]:
            raise ValueError("动画节点必须使用 TRS，不能对 matrix 节点直接施加通道")
        interpolation = sampler.get("interpolation", "LINEAR")
        if interpolation not in ("LINEAR", "STEP"):
            raise ValueError("首版不支持 glTF CUBICSPLINE 动画")
        name = {"translation": "position", "rotation": "rotation", "scale": "scale"}.get(target["path"])
        if name is None:
            raise ValueError("骨架运动入口不支持 morph weights 通道")
        fields = track_fields.setdefault(index_map[node_index], {})
        if name + "_times" in fields:
            raise ValueError("重复动画通道")
        fields[name + "_times"] = times
        fields[{"position": "positions", "rotation": "rotations", "scale": "scales"}[name]] = accessor(sampler["output"])
        fields[name + "_interpolation"] = interpolation
    tracks = []
    for index, fields in track_fields.items():
        for channel, width, values in (("position", 3, "positions"), ("rotation", 4, "rotations"), ("scale", 3, "scales")):
            fields.setdefault(channel + "_times", np.empty(0))
            fields.setdefault(values, np.empty((0, width)))
        tracks.append(NativeTrack(index, **fields))
    source = SourceInfo(f"{path.name}/animation_{animation_id}", hashes, "gltf_v1",
                        {"animation_id": animation_id, "animation_name": animation.get("name"), "skin_index": skin_index,
                         "node_indices": order, "ignored_animation_nodes": sorted(ignored_nodes),
                         "reference_policy": "node_reference_trs", "skin_joints": document["skins"][skin_index]["joints"]})
    motion = NativeMotion(skeleton, tracks, duration, SourceSpace(1.0, np.eye(3)), source)
    validate_native_motion(motion)
    return motion
