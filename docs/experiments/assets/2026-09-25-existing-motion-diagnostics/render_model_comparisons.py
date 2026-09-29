"""Render actual hybrid12 source/teacher-forced/closed-loop skeleton animations."""

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from data.runtime.conditioned_motion import load_raw, root_local
from inference.runtime.conditioned_pose import ConditionedPosePredictor
from motionbricks.data.unreal_dataset import apply_authoritative_root


ROOT = Path(__file__).resolve().parents[4]
RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
CHECKPOINT = Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_hybrid12\epoch_012.pt")
CLIPS = {"walk": 1306, "run": 983, "crouch": 49}
SIZE = (1440, 720)
FPS_PLAYBACK = 15
COLORS = {"source": "#56cfe1", "teacher": "#ffd166", "closed": "#ef6c96"}
KEEP = {"pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "head",
        "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l", "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
        "thigh_l", "calf_l", "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r"}
RIGHT = np.array([0.8, 0.0, 0.6], dtype=np.float32)
DEPTH = np.array([-0.6, 0.0, 0.8], dtype=np.float32)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_visible(pose_history, rotation_history, root_history, root_future, bones):
    return {"history_pose": pose_history, "history_rotations": rotation_history,
            "history_root_local": root_local(root_history, root_history[-1]),
            "future_root_plan_local": root_local(root_future, root_history[-1]),
            "reference_pose": np.zeros((24, bones, 3), dtype=np.float32),
            "reference_rotations": np.zeros((24, bones, 3, 3), dtype=np.float32),
            "reference_frame_mask": np.zeros(24, dtype=np.float32)}


def generate(index, predictor, contract):
    clip = contract["clips"][index]
    if clip["split"] != "validation" or clip["source_frames"] < 96:
        raise ValueError(f"Unexpected comparison clip {index}")
    raw, _ = load_raw(Path(contract["source_dataset"]) / clip["raw_file"],
                      clip["source_frames"], contract["bone_count"], contract["fps"],
                      expected_sha256=clip["raw_sha256"])
    bits = np.unpackbits(np.frombuffer(base64.b64decode(clip["contact_bits"]), dtype=np.uint8))
    contacts = bits[:clip["source_frames"] * 4].reshape(clip["source_frames"], 4).astype(bool)[24:96]
    pose_history = raw["positions"][:24].copy()
    rotation_history = raw["rotations"][:24].copy()
    teacher_parts = []
    closed_parts = []
    for chunk in range(3):
        middle = 24 + 24 * chunk
        end = middle + 24
        roots_before = raw["root_track"][middle - 24:middle]
        roots_future = raw["root_track"][middle:end]
        teacher = predictor.predict(make_visible(raw["positions"][middle - 24:middle],
                                                 raw["rotations"][middle - 24:middle],
                                                 roots_before, roots_future, contract["bone_count"]))
        if chunk == 0:
            closed = teacher
        else:
            closed = predictor.predict(make_visible(pose_history, rotation_history,
                                                    roots_before, roots_future, contract["bone_count"]))
        teacher_parts.append(teacher["future_pose"])
        closed_parts.append(closed["future_pose"])
        pose_history = closed["future_pose"]
        rotation_history = closed["future_rotations"]
    result = {"source": raw["positions"][24:96], "teacher": np.concatenate(teacher_parts),
              "closed": np.concatenate(closed_parts), "root": raw["root_track"][24:96],
              "contacts": contacts}
    if any(value.shape[0] != 72 or not np.isfinite(value).all() for value in result.values()):
        raise ValueError(f"Invalid generated sequence for {index}")
    return result


def project(world, root, offset_x, scale=165):
    center = root[:3] + np.array([0.0, 0.75, 0.0], dtype=np.float32)
    relative = world - center
    px = offset_x + 240 + scale * np.dot(relative, RIGHT)
    py = 380 - scale * (0.92 * relative[..., 1] - 0.2 * np.dot(relative, DEPTH))
    return np.stack((px, py), axis=-1)


def font(size):
    path = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default()


def draw_ground(draw, root, panel_x):
    x0, z0 = float(root[0]), float(root[2])
    for x in range(int(np.floor(x0)) - 4, int(np.floor(x0)) + 5):
        a = project(np.array([x, 0, z0 - 4]), root, panel_x)
        b = project(np.array([x, 0, z0 + 4]), root, panel_x)
        draw.line((*a.tolist(), *b.tolist()), fill="#233142", width=1)
    for z in range(int(np.floor(z0)) - 4, int(np.floor(z0)) + 5):
        a = project(np.array([x0 - 4, 0, z]), root, panel_x)
        b = project(np.array([x0 + 4, 0, z]), root, panel_x)
        draw.line((*a.tolist(), *b.tolist()), fill="#233142", width=1)


def draw_frame(index, frame, info, world, edges, foot_indices, title):
    image = Image.new("RGB", SIZE, "#0e1622")
    draw = ImageDraw.Draw(image)
    root = info["root"][frame]
    source = info["source"][frame]
    text_font, small_font = font(20), font(15)
    labels = (("source", "SOURCE ASSET"), ("teacher", "MODEL: TRUE HISTORY"),
              ("closed", "MODEL: GENERATED HISTORY"))
    for panel, (key, label) in enumerate(labels):
        x = panel * 480
        draw.rectangle((x + 3, 57, x + 477, 635), fill="#152232", outline="#34445a", width=2)
        draw_ground(draw, root, x)
        coords = project(world[key][frame], root, x)
        for parent, child in edges:
            draw.line((*coords[parent].tolist(), *coords[child].tolist()), fill=COLORS[key], width=3)
        for k, foot in enumerate(foot_indices):
            trail = world[key][max(0, frame - 10):frame + 1, foot]
            trace = project(trail, root, x)
            for a, b in zip(trace[:-1], trace[1:]):
                draw.line((*a.tolist(), *b.tolist()), fill="#76ed9a" if k == 0 else "#f8a65c", width=2)
            fx, fy = coords[foot]
            active = bool(info["contacts"][frame, 0 if k == 0 else 2])
            radius = 7 if active else 4
            draw.ellipse((fx - radius, fy - radius, fx + radius, fy + radius),
                         outline="#76ed9a" if k == 0 else "#f8a65c", width=2)
        error = float(np.sqrt(np.mean(np.sum((info[key][frame] - source) ** 2, axis=-1))) * 100)
        draw.text((x + 18, 75), label, font=text_font, fill=COLORS[key])
        draw.text((x + 18, 103), f"Joint error: {error:.1f} cm" if key != "source" else "Reference motion",
                  font=small_font, fill="#d5dfeb")
        draw.text((x + 18, 604), "Green/orange: last 10 foot positions", font=small_font, fill="#a9b8c9")
    draw.text((22, 14), f"{title}  |  source 30 Hz, playback 0.5x  |  frame {frame + 1:02d}/72",
              font=text_font, fill="#eff5ff")
    draw.text((22, 656), "All panels use the same exported Root; model has NO future pose reference.",
              font=small_font, fill="#d5dfeb")
    draw.text((22, 681), "Color rings use contact labels derived from the source motion. Skeleton preview; no UE skin/IK.",
              font=small_font, fill="#a9b8c9")
    draw.line((0, 642, SIZE[0], 642), fill="#34445a", width=2)
    for boundary in (24, 48):
        marker = int(boundary / 72 * (SIZE[0] - 80) + 40)
        draw.line((marker, 635, marker, 643), fill="#f0bd5b", width=2)
    progress = int((frame + 1) / 72 * (SIZE[0] - 80) + 40)
    draw.line((40, 641, progress, 641), fill="#6bbdea", width=4)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New local output directory for frames and model arrays")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    predictor = ConditionedPosePredictor(CHECKPOINT, RELEASE, LOCK)
    contract = predictor.contract
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    bones = skeleton["bones"]
    names = [bone["name"] for bone in bones]
    edges = [(bone["parent"], index) for index, bone in enumerate(bones)
             if bone["name"] in KEEP and bone["parent"] >= 0 and names[bone["parent"]] in KEEP]
    feet = (names.index("foot_l"), names.index("foot_r"))
    manifest = {"schema_version": 1, "contract_sha256": predictor.config["contract_sha256"],
                "checkpoint_sha256": sha256(CHECKPOINT), "checkpoint": "hybrid12 epoch_012",
                "fps_source": contract["fps"], "fps_playback": FPS_PLAYBACK,
                "condition": "no future pose reference; same exported source future Root; first 24 true history frames",
                "clips": []}
    for label, index in CLIPS.items():
        info = generate(index, predictor, contract)
        np.savez_compressed(args.output / f"{label}_{index}_source_teacher_closed.npz", **info)
        world = {key: apply_authoritative_root(info[key], info["root"])
                 for key in ("source", "teacher", "closed")}
        frames = args.output / f"{label}_{index}_frames"
        frames.mkdir()
        title = contract["clips"][index]["asset"].rsplit("/", 1)[-1].split(".")[0]
        for frame in range(72):
            image = draw_frame(index, frame, info, world, edges, feet, title)
            image.save(frames / f"frame_{frame:03d}.png")
        poster = ROOT / "docs/experiments/assets/2026-09-25-existing-motion-diagnostics" / f"{label}_{index}_poster.png"
        if poster.exists():
            raise FileExistsError(poster)
        shutil.copy2(frames / "frame_071.png", poster)
        video = poster.with_name(f"{label}_{index}_source_teacher_closed.mp4")
        if video.exists():
            raise FileExistsError(video)
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-framerate", str(FPS_PLAYBACK),
                   "-i", str(frames / "frame_%03d.png"), "-c:v", "libx264", "-crf", "23",
                   "-pix_fmt", "yuv420p", str(video)]
        subprocess.run(command, check=True)
        manifest["clips"].append({"clip_index": index, "asset": contract["clips"][index]["asset"],
                                  "video": video.name, "video_sha256": sha256(video),
                                  "poster": poster.name, "source_raw_sha256": contract["clips"][index]["raw_sha256"]})
        print(f"rendered {index}: {video}", flush=True)
    path = ROOT / "docs/experiments/assets/2026-09-25-existing-motion-diagnostics/render_manifest.json"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
