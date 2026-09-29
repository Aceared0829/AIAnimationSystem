"""Plot source versus hybrid12 foot speed on fixed validation contact frames."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from data.runtime.conditioned_motion import load_window
from inference.runtime.conditioned_pose import ConditionedPosePredictor
from motionbricks.data.unreal_dataset import apply_authoritative_root
from training.evaluation.evaluate_conditioned_baselines import select_windows


ROOT = Path(__file__).resolve().parents[4]
RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
CHECKPOINT = Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_hybrid12\epoch_012.pt")
OUT = Path(__file__).with_name("foot_contact_examples.png")
CLIPS = (1675, 393, 762)


def contact_frame_speeds(pose, root, contacts, feet, fps):
    world = apply_authoritative_root(pose, root)
    speed = np.linalg.norm(np.diff(world[:, feet], axis=0), axis=-1) * fps
    pairs = contacts[1:] & contacts[:-1]
    return np.array([float(speed[index, active].mean()) if active.any() else np.nan
                     for index, active in enumerate(pairs)])


def main():
    predictor = ConditionedPosePredictor(CHECKPOINT, RELEASE, LOCK)
    contract = predictor.contract
    source = Path(contract["source_dataset"])
    skeleton = json.loads((source / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in
            ("left_foot", "left_toe", "right_foot", "right_toe")]
    rows = {row["clip_index"]: row for row in select_windows(
        RELEASE / "contract/windows.jsonl", contract, "validation", 1)}
    figure, axes = plt.subplots(len(CLIPS), 1, figsize=(10, 8), sharex=True)
    for axis, index in zip(axes, CLIPS):
        sample = load_window(RELEASE / "contract", rows[index], contract=contract)
        predicted = predictor.predict(sample["input"])
        target = sample["target"]
        root = target["future_root_track"]
        contacts = target["future_contacts"]
        actual = contact_frame_speeds(target["future_pose"], root, contacts, feet, contract["fps"])
        model = contact_frame_speeds(predicted["future_pose"], root, contacts, feet, contract["fps"])
        frames = np.arange(1, 24)
        axis.plot(frames, actual, color="#167a52", marker="o", markersize=3, label="source")
        axis.plot(frames, model, color="#c2412d", marker="o", markersize=3, label="hybrid12 no reference")
        name = sample["metadata"]["asset"].rsplit("/", 1)[-1].split(".")[0]
        axis.set_title(f"{index} {name} | contact frame pairs: {np.isfinite(actual).sum()}", fontsize=10)
        axis.set_ylabel("world foot speed (m/s)")
        axis.grid(alpha=0.25)
        axis.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("future frame within the 24-frame window")
    figure.suptitle("Same exported Root and source-derived contact mask", fontsize=12)
    figure.tight_layout()
    figure.savefig(OUT, dpi=170)
    print(OUT)


if __name__ == "__main__":
    main()
