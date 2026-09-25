"""Render every frame of the four explicit stance clips for offline visual QA."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[4]
CONTRACT = json.loads(Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924\contract\contract.json").read_text(encoding="utf-8"))
SOURCE = Path(CONTRACT["source_dataset"])
SKELETON = json.loads((SOURCE / "skeleton.json").read_text(encoding="utf-8"))
OUT = ROOT / "output/p0_20260925/stance_filmstrips"
OUT.mkdir(parents=True, exist_ok=True)

KEEP = {"pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "head",
        "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l", "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
        "thigh_l", "calf_l", "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r"}
BONES = SKELETON["bones"]
EDGES = [(b["parent"], i) for i, b in enumerate(BONES)
         if b["name"] in KEEP and b["parent"] >= 0 and BONES[b["parent"]]["name"] in KEEP]


def point(p, left, top):
    return (round(left + 90 + p[0] * 72), round(top + 174 - p[1] * 115))


def render(index):
    clip = CONTRACT["clips"][index]
    path = SOURCE / clip["raw_file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != clip["raw_sha256"]:
        raise ValueError(f"SHA mismatch: {index}")
    with np.load(path, allow_pickle=False) as raw:
        positions = raw["positions"]
        root = raw["root_track"]
    if len(positions) != 76:
        raise ValueError(f"Unexpected frame count: {index}")
    canvas = Image.new("RGB", (1800, 1680), "white")
    draw = ImageDraw.Draw(canvas)
    for frame in range(len(positions)):
        left, top = frame % 10 * 180, frame // 10 * 210
        draw.rectangle((left, top, left + 179, top + 209), outline="#d9d9d9")
        draw.text((left + 5, top + 4), f"{index} | f{frame:02} | {frame/30:.2f}s", fill="#202020")
        draw.line((left + 12, top + 174, left + 168, top + 174), fill="#bcbcbc")
        for parent, child in EDGES:
            draw.line((point(positions[frame, parent], left, top),
                       point(positions[frame, child], left, top)), fill="#233955", width=2)
        px, py = point(positions[frame, 0], left, top)
        draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill="#c0392b")
        rx, ry = point(root[frame, :3], left, top)
        draw.ellipse((rx - 2, ry - 2, rx + 2, ry + 2), fill="#008e9e")
    target = OUT / f"stance_{index}_all_76_frames.png"
    canvas.save(target)
    print(target)


for index in (226, 227, 429, 430):
    render(index)
