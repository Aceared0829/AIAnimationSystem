"""通过显式指定的 Blender Headless 读取 FBX；无需 UE，缺少 Blender 时明确失败。"""

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from data.runtime.native_motion import (
    NativeMotion,
    NativeSkeleton,
    NativeTrack,
    SourceInfo,
    SourceSpace,
    validate_native_motion,
)


def read_fbx_motion(path, animation_id: str | None, blender: str) -> NativeMotion:
    path = Path(path).resolve()
    script = Path(__file__).resolve().parents[2] / "tools/read_fbx_native.py"
    with tempfile.TemporaryDirectory(prefix="motionweaver-fbx-") as temporary:
        output = Path(temporary) / "motion.json"
        command = [blender, "--background", "--factory-startup", "--python", str(script), "--", str(path), str(output)]
        if animation_id is not None:
            command.append(animation_id)
        result = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0 or not output.is_file():
            raise ValueError("Blender FBX 提取失败：" + (result.stderr or result.stdout)[-2000:])
        data = json.loads(output.read_text(encoding="utf-8"))
    fields = data["skeleton"]
    skeleton = NativeSkeleton(fields["names"], np.asarray(fields["parents"], dtype=np.int64),
                              np.asarray(fields["rest_positions"]), np.asarray(fields["rest_rotations"]), np.asarray(fields["rest_scales"]))
    times = np.asarray(data["timestamps"])
    tracks = [NativeTrack(i, times.copy(), np.asarray(track["positions"]), times.copy(), np.asarray(track["rotations"]),
                          times.copy(), np.asarray(track["scales"])) for i, track in enumerate(data["tracks"])]
    source = SourceInfo(f"{path.name}/{data['action']}", {str(path): hashlib.sha256(path.read_bytes()).hexdigest()}, "fbx_blender_v1",
                        {"action": data["action"], "bake_policy": "blender_source_frame_evaluation",
                         "source_fps": data["fps"], "blender_version": data["blender_version"],
                         "track_mask_policy": "evaluated_pose_all_components_not_original_fbx_channel_presence"})
    # Blender 的 Z-up 右手空间转换到 Motion Y-up 空间；角色实际朝向仍由来源骨架定义。
    motion = NativeMotion(skeleton, tracks, float(times[-1]),
                          SourceSpace(data["meters_per_unit"], np.array([[1., 0, 0], [0, 0, 1], [0, -1, 0]])), source)
    validate_native_motion(motion)
    return motion
