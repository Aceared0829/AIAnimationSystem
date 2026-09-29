"""Render source/uniform12/fine-tuned generated-history model comparisons."""

import argparse
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from inference.runtime.conditioned_pose import ConditionedPosePredictor
from motionbricks.data.unreal_dataset import apply_authoritative_root


ROOT = Path(__file__).resolve().parents[4]
OLD_SCRIPT = ROOT / "docs/experiments/assets/2026-09-25-existing-motion-diagnostics/render_model_comparisons.py"
BASE = Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_uniform12\epoch_012.pt")
NEW = Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02\generated_contact\epoch_010.pt")
CLIPS = {"walk": 1306, "run": 983, "crouch": 49}
COLORS = {"source": "#56cfe1", "baseline": "#ef6c96", "optimized": "#8ce6a5"}


def load_helpers():
    spec = importlib.util.spec_from_file_location("old_motion_renderer", OLD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def draw_frame(helpers, frame, info, world, edges, feet, title):
    image = Image.new("RGB", (1440, 720), "#0e1622")
    draw = ImageDraw.Draw(image)
    root = info["root"][frame]
    labels = (("source", "SOURCE ASSET"), ("baseline", "UNIFORM12: CLOSED LOOP"),
              ("optimized", "FINE TUNED: CLOSED LOOP"))
    for panel, (key, label) in enumerate(labels):
        x = panel * 480
        draw.rectangle((x + 3, 57, x + 477, 635), fill="#152232", outline="#34445a", width=2)
        helpers.draw_ground(draw, root, x)
        coords = helpers.project(world[key][frame], root, x)
        for parent, child in edges:
            draw.line((*coords[parent].tolist(), *coords[child].tolist()), fill=COLORS[key], width=3)
        for number, foot in enumerate(feet):
            trail = helpers.project(world[key][max(0, frame - 10):frame + 1, foot], root, x)
            for a, b in zip(trail[:-1], trail[1:]):
                draw.line((*a.tolist(), *b.tolist()), fill="#76ed9a" if number == 0 else "#f8a65c", width=2)
            fx, fy = coords[foot]
            active = bool(info["contacts"][frame, 0 if number == 0 else 2])
            radius = 7 if active else 4
            draw.ellipse((fx - radius, fy - radius, fx + radius, fy + radius),
                         outline="#76ed9a" if number == 0 else "#f8a65c", width=2)
        draw.text((x + 18, 75), label, font=helpers.font(19), fill=COLORS[key])
        if key != "source":
            error = float(np.sqrt(np.mean(np.sum((info[key][frame] - info["source"][frame]) ** 2,
                                                   axis=-1))) * 100)
            draw.text((x + 18, 105), f"Joint error: {error:.1f} cm", font=helpers.font(15), fill="#d5dfeb")
        draw.text((x + 18, 604), "Green/orange: last 10 foot positions",
                  font=helpers.font(15), fill="#a9b8c9")
    draw.text((22, 14), f"{title}  |  0.5x playback  |  frame {frame + 1:02d}/72",
              font=helpers.font(20), fill="#eff5ff")
    draw.line((0, 642, 1440, 642), fill="#34445a", width=2)
    draw.line((40, 641, int((frame + 1) / 72 * 1360 + 40), 641), fill="#6bbdea", width=4)
    draw.text((22, 657), "Both models feed back their own generated history. Same source future Root; no pose reference.",
              font=helpers.font(15), fill="#d5dfeb")
    draw.text((22, 681), "Source-derived contact rings. Skeleton preview only; no UE mesh, IK, or live controller.",
              font=helpers.font(15), fill="#a9b8c9")
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-output", type=Path, required=True)
    parser.add_argument("--media-output", type=Path, required=True)
    args = parser.parse_args()
    if args.frames_output.exists() or args.media_output.exists():
        raise FileExistsError("outputs must be new directories")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    args.frames_output.mkdir(parents=True)
    args.media_output.mkdir(parents=True)
    helper = load_helpers()
    base = ConditionedPosePredictor(BASE, helper.RELEASE, helper.LOCK)
    optimized = ConditionedPosePredictor(NEW, helper.RELEASE, helper.LOCK)
    contract = base.contract
    if optimized.config["contract_sha256"] != base.config["contract_sha256"]:
        raise ValueError("contract mismatch")
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    bones = skeleton["bones"]
    names = [bone["name"] for bone in bones]
    edges = [(bone["parent"], index) for index, bone in enumerate(bones)
             if bone["name"] in helper.KEEP and bone["parent"] >= 0
             and names[bone["parent"]] in helper.KEEP]
    feet = (names.index("foot_l"), names.index("foot_r"))
    manifest = {"schema_version": 1, "baseline_sha256": helper.sha256(BASE),
                "optimized_sha256": helper.sha256(NEW),
                "condition": "no reference; model-generated history; source future Root",
                "clips": []}
    for label, index in CLIPS.items():
        old = helper.generate(index, base, contract)
        new = helper.generate(index, optimized, contract)
        if not np.array_equal(old["root"], new["root"]) or not np.array_equal(old["source"], new["source"]):
            raise ValueError("comparison conditions differ")
        info = {"source": old["source"], "baseline": old["closed"],
                "optimized": new["closed"], "root": old["root"], "contacts": old["contacts"]}
        world = {key: apply_authoritative_root(info[key], info["root"])
                 for key in ("source", "baseline", "optimized")}
        frames = args.frames_output / f"{label}_{index}"
        frames.mkdir()
        title = contract["clips"][index]["asset"].rsplit("/", 1)[-1].split(".")[0]
        for frame in range(72):
            draw_frame(helper, frame, info, world, edges, feet, title).save(frames / f"frame_{frame:03d}.png")
        video = args.media_output / f"{label}_{index}_baseline_vs_optimized.mp4"
        poster = args.media_output / f"{label}_{index}_poster.png"
        shutil.copy2(frames / "frame_071.png", poster)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-framerate", "15",
                        "-i", str(frames / "frame_%03d.png"), "-c:v", "libx264", "-crf", "23",
                        "-pix_fmt", "yuv420p", str(video)], check=True)
        manifest["clips"].append({"clip_index": index, "asset": contract["clips"][index]["asset"],
                                  "video": video.name, "video_sha256": helper.sha256(video),
                                  "poster": poster.name})
        print(f"rendered {label}: {video}", flush=True)
    (args.media_output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
