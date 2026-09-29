"""Plot UE world foot-bone speed at source-labelled stance frame pairs."""

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


FEET = ("foot_l", "ball_l", "foot_r", "ball_r")


def bones(path):
    values = {}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            key = (row["scenario"], row["lane"])
            values.setdefault(key, np.full((72, 4, 3), np.nan))
            values[key][int(row["frame"]), FEET.index(row["bone"])] = [
                float(row[f"world_{axis}_cm"]) for axis in "xyz"]
    if any(not np.isfinite(value).all() for value in values.values()):
        raise ValueError("Missing bone rows")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    a, b = bones(args.control / "bone_readback.csv"), bones(args.candidate / "bone_readback.csv")
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    for ax, scenario in zip(axes, ("walk", "run", "crouch")):
        contacts = np.fromfile(args.fixtures / scenario / "source_contacts.f32", dtype="<f4").reshape(72, 4) > .5
        paired = contacts[1:] & contacts[:-1]
        for label, value, lane, color in (("Source pose + CMC", a, "source_cmc", "#259a68"),
                                          ("Matched control", a, "model_cmc", "#466cb7"),
                                          ("Speed/phase pilot", b, "model_cmc", "#d47730")):
            speed = np.linalg.norm(np.diff(value[(scenario, lane)], axis=0), axis=-1) * .3
            frame_mean = np.array([float(speed[i, paired[i]].mean()) if paired[i].any() else np.nan
                                   for i in range(71)])
            ax.plot(np.arange(1, 72), frame_mean, label=label, color=color, marker="o", markersize=2,
                    linewidth=1.2)
        ax.set_title(f"{scenario.capitalize()} — {int(paired.sum())} source-labelled foot pairs")
        ax.set_ylabel("UE foot speed (m/s)")
        ax.grid(alpha=.2)
    axes[-1].set_xlabel("Frame (30 Hz source time)")
    axes[0].legend(ncol=3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
