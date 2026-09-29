"""Package four UE skinned lanes with contact-foot speeds read back from UE."""

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


SCENARIOS = ("walk", "run", "crouch")
LANES = (
    ("source_source", "SOURCE POSE + SOURCE ROOT"),
    ("source_cmc", "SOURCE POSE + MATCHED CMC"),
    ("model_plan", "MODEL POSE + ROOT PLAN"),
    ("model_cmc", "MODEL POSE + EXECUTED CMC"),
)
FEET = ("foot_l", "ball_l", "foot_r", "ball_r")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bones(path):
    bones = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            key = (row["scenario"], row["lane"], int(row["frame"]), row["bone"])
            bones[key] = np.array([float(row[f"world_{axis}_cm"]) for axis in "xyz"], dtype=np.float64)
    return bones


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-frames", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--work-frames", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--ue-log", type=Path, required=True)
    args = parser.parse_args()
    if args.work_frames.exists() or args.media.exists():
        raise FileExistsError("packaged outputs must not already exist")
    args.work_frames.mkdir(parents=True)
    args.media.mkdir(parents=True)
    bones = read_bones(args.raw_frames / "bone_readback.csv")
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 17)
    small = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 14)
    manifest = {"schema_version": 1, "source": "UE 5.8.2 NNE CPU plus UEFN skinned mesh and world-bone readback",
                "display_transform": "RGB channel = clamp((UE PNG channel - 4) * 6, 0, 255); labels only",
                "source_fps": 30, "video_fps": 15, "frames_per_scenario": 72,
                "ue_log_sha256": sha256(args.ue_log),
                "bone_readback_sha256": sha256(args.raw_frames / "bone_readback.csv"), "videos": []}
    for scenario in SCENARIOS:
        contacts = np.fromfile(args.fixtures / scenario / "source_contacts.f32", dtype="<f4").reshape(72, 4) > 0.5
        folder = args.work_frames / scenario
        folder.mkdir()
        for frame in range(72):
            canvas = Image.new("RGB", (1280, 720), (18, 25, 34))
            for index, (lane, label) in enumerate(LANES):
                with Image.open(args.raw_frames / scenario / lane / f"frame_{frame:03d}.png") as source:
                    if source.size != (640, 360):
                        raise ValueError(f"invalid UE frame size: {scenario}/{lane}/{frame}")
                    rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
                panel = Image.fromarray(np.clip((rgb - 4) * 6, 0, 255).astype(np.uint8), "RGB")
                draw = ImageDraw.Draw(panel)
                draw.rectangle((0, 0, 640, 39), fill=(18, 25, 34))
                draw.text((12, 7), label, font=font, fill=(211, 236, 255) if index < 2 else (191, 255, 199))
                draw.rectangle((0, 329, 640, 360), fill=(18, 25, 34))
                paired = contacts[frame] & contacts[frame - 1] if frame else np.zeros(4, dtype=bool)
                if paired.any():
                    speeds = [np.linalg.norm(bones[(scenario, lane, frame, foot)] - bones[(scenario, lane, frame - 1, foot)]) * 0.3
                              for foot, contact in zip(FEET, paired) if contact]
                    value = float(np.mean(speeds))
                    color = (141, 238, 172) if value < 0.15 else (255, 217, 131) if value < 0.5 else (255, 150, 142)
                    text = f"Source-stance foot speed {value:.2f} m/s"
                else:
                    color, text = (187, 204, 224), "No source-stance foot pair"
                draw.text((12, 335), text, font=small, fill=color)
                canvas.paste(panel, ((index % 2) * 640, (index // 2) * 360))
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((0, 356, 1280, 360), fill=(129, 151, 176))
            draw.rectangle((636, 0, 640, 720), fill=(129, 151, 176))
            draw.text((1090, 697), f"{scenario.upper()} {frame + 1}/72", font=small, fill=(255, 255, 255))
            canvas.save(folder / f"frame_{frame:03d}.png")
        poster = args.media / f"{scenario}_four_way_poster.png"
        video = args.media / f"{scenario}_four_way.mp4"
        shutil.copy2(folder / "frame_071.png", poster)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-framerate", "15", "-i",
                        str(folder / "frame_%03d.png"), "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                        str(video)], check=True)
        manifest["videos"].append({"scenario": scenario, "video": video.name, "video_sha256": sha256(video),
                                   "poster": poster.name, "poster_sha256": sha256(poster)})
        print(f"packaged {scenario}: {video}", flush=True)
    (args.media / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
