"""Package matched CMC skinned source/control/candidate views from UE renders."""

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
FEET = ("foot_l", "ball_l", "foot_r", "ball_r")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_bones(path):
    out = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            key = (row["scenario"], row["lane"])
            out.setdefault(key, np.zeros((72, 4, 3), dtype=np.float64))
            out[key][int(row["frame"]), FEET.index(row["bone"])] = [
                float(row[f"world_{axis}_cm"]) for axis in "xyz"]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True)
    args = parser.parse_args()
    if args.work.exists() or args.media.exists():
        raise FileExistsError("Output directories must be new")
    args.work.mkdir(parents=True)
    args.media.mkdir(parents=True)
    control_bones = read_bones(args.control / "bone_readback.csv")
    candidate_bones = read_bones(args.candidate / "bone_readback.csv")
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 18)
    small = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 15)
    report = {"schema_version": 1, "condition": "Same source clip and matched recorded CMC Root; UE NNE CPU skinned mesh",
              "source_fps": 30, "video_fps": 15, "frames_per_scenario": 72,
              "display_transform": "clamp((UE RGB - 4) * 6, 0, 255); presentation only",
              "control_bones_sha256": sha256(args.control / "bone_readback.csv"),
              "candidate_bones_sha256": sha256(args.candidate / "bone_readback.csv"), "videos": []}
    for scenario in SCENARIOS:
        contacts = np.fromfile(args.fixtures / scenario / "source_contacts.f32", dtype="<f4").reshape(72, 4) > .5
        folder = args.work / scenario
        folder.mkdir()
        views = ((args.control, "source_cmc", "SOURCE + MATCHED CMC", control_bones),
                 (args.control, "model_cmc", "MATCHED CONTROL", control_bones),
                 (args.candidate, "model_cmc", "SPEED/PHASE PILOT", candidate_bones))
        for frame in range(72):
            canvas = Image.new("RGB", (1920, 360), (18, 25, 34))
            for panel_index, (source_dir, lane, title, bones) in enumerate(views):
                with Image.open(source_dir / scenario / lane / f"frame_{frame:03d}.png") as raw:
                    rgb = np.asarray(raw.convert("RGB"), dtype=np.float32)
                panel = Image.fromarray(np.clip((rgb - 4) * 6, 0, 255).astype(np.uint8), "RGB")
                draw = ImageDraw.Draw(panel)
                draw.rectangle((0, 0, 640, 39), fill=(18, 25, 34))
                draw.text((12, 7), title, font=font,
                          fill=(211, 236, 255) if panel_index == 0 else (191, 255, 199))
                draw.rectangle((0, 329, 640, 360), fill=(18, 25, 34))
                paired = contacts[frame] & contacts[frame - 1] if frame else np.zeros(4, dtype=bool)
                if paired.any():
                    speed = np.linalg.norm(bones[(scenario, lane)][frame] -
                                           bones[(scenario, lane)][frame - 1], axis=-1) * .3
                    text = f"Source-labelled foot speed: {float(speed[paired].mean()):.2f} m/s"
                else:
                    text = "No source-labelled foot pair"
                draw.text((12, 335), text, font=small, fill=(255, 217, 131))
                canvas.paste(panel, (panel_index * 640, 0))
            draw = ImageDraw.Draw(canvas)
            draw.text((1790, 335), f"{frame+1}/72", font=small, fill=(255, 255, 255))
            canvas.save(folder / f"frame_{frame:03d}.png")
        poster = args.media / f"{scenario}_poster.png"
        video = args.media / f"{scenario}_control_vs_speed_phase.mp4"
        poster_frame = {"walk": 55, "run": 56, "crouch": 55}[scenario]
        shutil.copy2(folder / f"frame_{poster_frame:03d}.png", poster)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-framerate", "15",
                        "-i", str(folder / "frame_%03d.png"), "-c:v", "libx264", "-crf", "20",
                        "-pix_fmt", "yuv420p", str(video)], check=True)
        report["videos"].append({"scenario": scenario, "video": video.name,
                                 "video_sha256": sha256(video), "poster": poster.name,
                                 "poster_sha256": sha256(poster)})
        print(f"packaged {scenario}: {video}", flush=True)
    (args.media / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
