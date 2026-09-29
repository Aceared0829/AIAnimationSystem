"""Compare local MotionWeaver and old-model reports on identical held-out windows.

The input reports must contain the same source world joints, Actor Root track,
and source contact mask. This rejects comparisons that silently change either
trajectory or sample timing. Lower is better for the selected error metrics.
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from inference.visualization.motionweaver_preview import sha256


METRICS = (
    "joint_rmse_cm",
    "joint_mean_error_cm",
    "foot_velocity_rmse_mps",
    "generated_contact_foot_speed_mps",
    "seam_velocity_error_cm_per_frame",
    "body_facing_rmse_vs_source_deg",
)


def compare(old_dir, new_dir, output, video=False, allow_untrained_smoke=False):
    old_dir, new_dir, output = Path(old_dir), Path(new_dir), Path(output)
    if output.exists():
        raise FileExistsError(output)
    old = json.loads((old_dir / "report.json").read_text(encoding="utf-8"))
    new = json.loads((new_dir / "report.json").read_text(encoding="utf-8"))
    if new.get("condition_mode") != "actor":
        raise ValueError("Only Actor-conditioned MotionWeaver is comparable to this baseline")
    if (new.get("decoder_pose_root_oracle")
            or new["input_visibility"].get("future_source_pose_feature_root_frames") != 0):
        raise ValueError("Causal comparison cannot use future source pose-feature Root")
    if not new.get("pose_checkpoint_has_training_steps") and not allow_untrained_smoke:
        raise ValueError("MotionWeaver checkpoint has no verified training steps; use --allow-untrained-smoke only for pipeline tests")
    if old.get("split") != "test" or new.get("split") != "test":
        raise ValueError("Both reports must use held-out test clips")
    if old["dataset_manifest_sha256"] != new["dataset_manifest_sha256"]:
        raise ValueError("Dataset manifests differ")
    if old["skeleton_sha256"] != new["skeleton_sha256"]:
        raise ValueError("Skeletons differ")
    old_entries = {entry["clip_index"]: entry for entry in old["clips"]}
    new_entries = {entry["clip_index"]: entry for entry in new["clips"]}
    if old_entries.keys() != new_entries.keys():
        raise ValueError("Clip sets differ")
    report = {
        "schema_version": 1,
        "scope": "same-source, same-Actor-Root offline skeleton comparison; no live CMC/UE skin",
        "old_checkpoint_sha256": old["checkpoint_sha256"],
        "motionweaver_checkpoint_sha256": new["pose_checkpoint_sha256"],
        "motionweaver_training_steps": new.get("pose_checkpoint_training_steps"),
        "motionweaver_run_label": new.get("run_label", ""),
        "untrained_smoke_only": not new.get("pose_checkpoint_has_training_steps"),
        "old_history_pose_frames": old["input_visibility"]["historical_source_pose_frames"],
        "motionweaver_history_pose_frames": new["input_visibility"]["historical_source_pose_frames"],
        "future_source_pose_frames": 0,
        "future_actor_root_source": new["actor_root_source"],
        "comparison_limits": [
            "Different history lengths: old model 24 frames, MotionWeaver 4 frames",
            "The future Actor Root is exported from the source clip; it is an offline controller-plan proxy",
            "Contact speed is omitted when no consecutive source-contact pairs exist",
            "World translation is imposed by the same Actor Root in both models, so its equality is not a quality win",
        ],
        "clips": [],
    }
    output.mkdir(parents=True)
    for index in sorted(old_entries):
        old_entry, new_entry = old_entries[index], new_entries[index]
        if (old_entry["category"] != new_entry["category"]
                or old_entry["asset"] != new_entry["asset"]
                or old_entry["source_frame_start"] != new_entry["source_frame_start"]
                or old_entry["source_frames"] != new_entry["source_frames"]
                or old_entry["future_frames_scored"] != new_entry["metrics"]["evaluated_frames"]):
            raise ValueError(f"Clip {index} has different timing or identity")
        with np.load(old_dir / old_entry["arrays"], allow_pickle=False) as old_arrays, \
                np.load(new_dir / new_entry["arrays"], allow_pickle=False) as new_arrays:
            for name in ("source", "actor_root"):
                if not np.array_equal(old_arrays[name], new_arrays[name]):
                    raise ValueError(f"Clip {index} has different {name} values")
            if not np.array_equal(old_arrays["source_contacts"] > 0.5,
                                  new_arrays["source_contacts"] > 0.5):
                raise ValueError(f"Clip {index} has different source contact masks")
        metrics = {}
        for name in METRICS:
            old_value = old_entry["metrics"].get(name)
            new_value = new_entry["metrics"].get(name)
            metrics[name] = {
                "old": old_value, "motionweaver": new_value,
                "motionweaver_minus_old": (
                    float(new_value - old_value)
                    if old_value is not None and new_value is not None else None
                ),
            }
        entry = {"clip_index": index, "category": old_entry["category"],
                 "asset": old_entry["asset"], "source_frame_start": old_entry["source_frame_start"],
                 "future_frames": old_entry["future_frames_scored"],
                 "source_contact_pairs": old_entry["metrics"]["source_contact_pairs"],
                 "source_contact_foot_speed_mps": old_entry["metrics"]["source_contact_foot_speed_mps"],
                 "metrics": metrics}
        if video:
            if "video" not in old_entry or "video" not in new_entry:
                raise ValueError("Both input reports need videos for --video")
            if not shutil.which("ffmpeg"):
                raise RuntimeError("ffmpeg is required for --video")
            result_video = output / f"{old_entry['category'].lower()}_{index:05d}_comparison.mp4"
            # Old video contains Source | Old. Crop the right half of the new
            # video to append MotionWeaver as the third synchronized panel.
            command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                       "-i", str(old_dir / old_entry["video"]),
                       "-i", str(new_dir / new_entry["video"]),
                       "-filter_complex", "[1:v]crop=640:720:640:0[new];[0:v][new]hstack=inputs=2[out]",
                       "-map", "[out]", "-an", "-c:v", "libx264", "-crf", "22",
                       "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(result_video)]
            subprocess.run(command, check=True)
            entry["video"] = result_video.name
            entry["video_sha256"] = sha256(result_video)
            still = result_video.with_suffix(".png")
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(result_video), "-vf", "select=eq(n\\,14)",
                 "-frames:v", "1", str(still)], check=True,
            )
            entry["representative_frame_png"] = still.name
            entry["representative_frame_sha256"] = sha256(still)
        report["clips"].append(entry)
    (output / "comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--motionweaver", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--allow-untrained-smoke", action="store_true")
    args = parser.parse_args()
    result = compare(args.old, args.motionweaver, args.output, args.video,
                     args.allow_untrained_smoke)
    print(json.dumps(result, ensure_ascii=False, indent=2))
