"""Package exact UE render frames as labeled comparison videos with display-only contrast."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


SCENARIOS = ("walk", "run", "crouch", "stand_to_crouch")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-frames", type=Path, required=True)
    parser.add_argument("--work-frames", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--ue-log", type=Path, required=True)
    args = parser.parse_args()
    if args.work_frames.exists() or args.media.exists():
        raise FileExistsError("packaging output must not already exist")
    args.work_frames.mkdir(parents=True)
    args.media.mkdir(parents=True)
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 19)
    small = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 15)
    manifest = {"schema_version": 1, "source": "UE 5.8.2 NNE CPU inference on prepared CMC inputs; "
                "UPoseableMeshComponent skinned UEFN Mannequin; UE SceneCapture BaseColor frames",
                "display_transform": "RGB channel = clamp((UE PNG channel - 4) * 6, 0, 255); labels only",
                "fps": 15, "source_fps": 30, "frames_per_scenario": 72,
                "ue_log_sha256": sha256(args.ue_log), "videos": []}
    for name in SCENARIOS:
        folder = args.work_frames / name
        folder.mkdir()
        for frame in range(72):
            source = args.raw_frames / name / f"frame_{frame:03d}.png"
            with Image.open(source) as image:
                if image.size != (960, 540):
                    raise ValueError(f"wrong UE frame size: {source}")
                rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
            enhanced = Image.fromarray(np.clip((rgb - 4) * 6, 0, 255).astype(np.uint8), "RGB")
            draw = ImageDraw.Draw(enhanced)
            draw.rectangle((0, 0, 960, 47), fill=(17, 25, 35))
            draw.text((18, 12), "OLD  uniform12", fill=(255, 180, 186), font=font)
            draw.text((500, 12), "NEW  generated history + contact", fill=(173, 255, 203), font=font)
            draw.rectangle((0, 505, 960, 540), fill=(17, 25, 35))
            status = "CROUCH ACCEPTED" if name == "stand_to_crouch" and frame >= 24 else ""
            draw.text((18, 513), f"UE NNE + skinned mesh  |  {name.upper()}  |  frame {frame + 1}/72", fill="white", font=small)
            if status:
                draw.text((760, 513), status, fill=(255, 207, 111), font=small)
            draw.line((480, 47, 480, 505), fill=(150, 166, 184), width=2)
            enhanced.save(folder / f"frame_{frame:03d}.png")
        video = args.media / f"{name}_ue_skinned.mp4"
        poster = args.media / f"{name}_poster.png"
        shutil.copy2(folder / "frame_071.png", poster)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-framerate", "15",
                        "-i", str(folder / "frame_%03d.png"), "-c:v", "libx264", "-crf", "19",
                        "-pix_fmt", "yuv420p", str(video)], check=True)
        manifest["videos"].append({"scenario": name, "video": video.name,
                                   "video_sha256": sha256(video), "poster": poster.name,
                                   "poster_sha256": sha256(poster)})
        print(f"packaged {video}", flush=True)
    (args.media / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
