"""Render model responses to real UE CMC Root and a held-command plan."""

import argparse
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from motionbricks.data.unreal_dataset import apply_authoritative_root


ROOT = Path(__file__).resolve().parents[4]
OLD_SCRIPT = ROOT / "docs/experiments/assets/2026-09-25-existing-motion-diagnostics/render_model_comparisons.py"
LABELS = ("walk", "run", "crouch", "stand_to_crouch")
COLORS = {"uniform12": "#ef6c96", "optimized": "#8ce6a5"}


def load_helpers():
    spec = importlib.util.spec_from_file_location("old_motion_renderer", OLD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def draw_frame(helper, label, frame, data, world, edges, feet):
    image = Image.new("RGB", (1440, 720), "#0e1622")
    draw = ImageDraw.Draw(image)
    root = data["accepted_root"][frame]
    for panel, (key, name) in enumerate((("uniform12", "UNIFORM12: SCRIPTED CMC"),
                                          ("optimized", "FINE TUNED: SCRIPTED CMC"))):
        x = panel * 480
        draw.rectangle((x + 3, 57, x + 477, 635), fill="#152232", outline="#34445a", width=2)
        helper.draw_ground(draw, root, x)
        coords = helper.project(world[key][frame], root, x)
        for parent, child in edges:
            draw.line((*coords[parent].tolist(), *coords[child].tolist()), fill=COLORS[key], width=3)
        for leg, foot in enumerate(feet):
            trail = helper.project(world[key][max(0, frame - 10):frame + 1, foot], root, x)
            for a, b in zip(trail[:-1], trail[1:]):
                draw.line((*a.tolist(), *b.tolist()), fill="#76ed9a" if leg == 0 else "#f8a65c", width=2)
            fx, fy = coords[foot]
            draw.ellipse((fx - 4, fy - 4, fx + 4, fy + 4),
                         outline="#76ed9a" if leg == 0 else "#f8a65c", width=2)
        draw.text((x + 18, 75), name, font=helper.font(18), fill=COLORS[key])
        draw.text((x + 18, 105), "Model sees held-command Root plan", font=helper.font(15), fill="#d5dfeb")
        draw.text((x + 18, 604), "Displayed Root = executed CMC capsule bottom", font=helper.font(15), fill="#a9b8c9")

    x = 960
    draw.rectangle((x + 3, 57, x + 477, 635), fill="#152232", outline="#34445a", width=2)
    draw.text((x + 18, 75), "ROOT PATH, TOP VIEW", font=helper.font(19), fill="#dbe5f4")
    actual = data["accepted_root"][:, [0, 2]]
    planned = data["command_root_plan"][:, [0, 2]]
    combined = np.concatenate((actual, planned))
    center = 0.5 * (combined.min(axis=0) + combined.max(axis=0))
    extent = np.maximum(combined.max(axis=0) - combined.min(axis=0), 0.5)
    scale = min(350 / extent[0], 380 / extent[1], 180)
    def map_points(values):
        return np.stack((1200 + (values[:, 0] - center[0]) * scale,
                         370 - (values[:, 1] - center[1]) * scale), axis=-1)
    accepted_px = map_points(actual[:frame + 1])
    planned_px = map_points(planned[:frame + 1])
    if len(accepted_px) > 1:
        draw.line([tuple(p) for p in accepted_px], fill="#56cfe1", width=3)
        draw.line([tuple(p) for p in planned_px], fill="#ffd166", width=3)
    for value, color in ((accepted_px[-1], "#56cfe1"), (planned_px[-1], "#ffd166")):
        draw.ellipse((value[0] - 6, value[1] - 6, value[0] + 6, value[1] + 6), fill=color)
    error_cm = float(np.linalg.norm(data["accepted_root"][frame, :3] -
                                    data["command_root_plan"][frame, :3]) * 100)
    draw.text((x + 18, 555), f"Plan vs accepted Root: {error_cm:.1f} cm", font=helper.font(17), fill="#dbe5f4")
    draw.text((x + 18, 582), "Blue: executed CMC | Yellow: command plan", font=helper.font(14), fill="#a9b8c9")
    state = "CROUCH ACCEPTED" if data["accepted_crouch"][frame] else "STAND ACCEPTED"
    draw.text((x + 18, 105), state, font=helper.font(15), fill="#d5dfeb")

    draw.text((22, 14), f"{label.upper()}  |  UE 5.8.2 CMC trace  |  0.5x  |  frame {frame + 1:02d}/72",
              font=helper.font(20), fill="#eff5ff")
    draw.line((0, 642, 1440, 642), fill="#34445a", width=2)
    draw.line((40, 641, int((frame + 1) / 72 * 1360 + 40), 641), fill="#6bbdea", width=4)
    draw.text((22, 657), "No future source motion. Future commands held per 24-frame plan; executed CMC path is recorded separately.",
              font=helper.font(15), fill="#d5dfeb")
    draw.text((22, 681), "CMC ground-aligned Root with Python model poses. No UE skin/IK or deployed model runtime.",
              font=helper.font(15), fill="#a9b8c9")
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--frames-output", type=Path, required=True)
    parser.add_argument("--media-output", type=Path, required=True)
    args = parser.parse_args()
    if args.frames_output.exists() or args.media_output.exists():
        raise FileExistsError("outputs must be new")
    args.frames_output.mkdir(parents=True)
    args.media_output.mkdir(parents=True)
    helper = load_helpers()
    skeleton = json.loads((Path(r"E:\AIAnimationSystemData\prepared\native30_traversal_semantic_v1") /
                           "skeleton.json").read_text(encoding="utf-8"))
    bones = skeleton["bones"]
    names = [bone["name"] for bone in bones]
    edges = [(bone["parent"], index) for index, bone in enumerate(bones)
             if bone["name"] in helper.KEEP and bone["parent"] >= 0
             and names[bone["parent"]] in helper.KEEP]
    feet = (names.index("foot_l"), names.index("foot_r"))
    manifest = {"schema_version": 1, "inference_summary": str(args.inference / "summary.json"),
                "pose_root": "CMC capsule bottom, not capsule center",
                "trace_sha256": json.loads((args.inference / "summary.json").read_text())["trace_sha256"],
                "clips": []}
    for label in LABELS:
        with np.load(args.inference / f"{label}_cmc_root.npz") as archive:
            data = {key: archive[key] for key in archive.files}
        root = data["accepted_root"]
        world = {"uniform12": apply_authoritative_root(data["pose_command_plan_uniform12"], root),
                 "optimized": apply_authoritative_root(data["pose_command_plan_generated_contact10"], root)}
        folder = args.frames_output / label
        folder.mkdir()
        for frame in range(72):
            draw_frame(helper, label, frame, data, world, edges, feet).save(folder / f"frame_{frame:03d}.png")
        poster = args.media_output / f"{label}_cmc_poster.png"
        video = args.media_output / f"{label}_cmc_root_comparison.mp4"
        shutil.copy2(folder / "frame_071.png", poster)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-framerate", "15",
                        "-i", str(folder / "frame_%03d.png"), "-c:v", "libx264", "-crf", "23",
                        "-pix_fmt", "yuv420p", str(video)], check=True)
        manifest["clips"].append({"scenario": label, "video": video.name,
                                  "video_sha256": helper.sha256(video), "poster": poster.name})
        print(f"rendered CMC {label}: {video}", flush=True)
    (args.media_output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
