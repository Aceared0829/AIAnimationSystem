"""Plot the two completed A800 training runs from their local CSV logs."""

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[4]
DESTINATION = Path(__file__).resolve().parent
RUNS = {
    "2k chain pilot": PROJECT / "output/motionweaver_actor_a800_20260928/metrics.csv",
    "20k formal": PROJECT / "output/motionweaver_actor_a800_20k_20260928/metrics.csv",
}


def read_steps(path):
    with path.open(newline="", encoding="utf-8") as stream:
        rows = csv.DictReader(stream)
        return [(int(row["step"]), float(row["loss/train_loss_step"]))
                for row in rows if row.get("loss/train_loss_step")]


def smooth(values, width=200):
    kernel = np.ones(width) / width
    return np.convolve(values, kernel, mode="valid")


def main():
    figure, ax = plt.subplots(figsize=(10, 4.4), dpi=160)
    report = {}
    for label, path in RUNS.items():
        points = read_steps(path)
        steps = np.asarray([step for step, _ in points])
        losses = np.asarray([value for _, value in points])
        width = min(200, len(losses))
        ax.plot(steps[width - 1:], smooth(losses, width), label=label, linewidth=1.7)
        report[label] = {
            "logged_steps": len(points),
            "last_step": int(steps[-1]),
            "first_100_mean_token_ce_nats": float(losses[:100].mean()),
            "last_100_mean_token_ce_nats": float(losses[-100:].mean()),
            "source": str(path),
        }
    ax.set(title="MotionWeaver Actor Root Pose Token training",
           xlabel="Optimizer step", ylabel="Training token cross entropy (nats)")
    ax.grid(alpha=0.2)
    ax.legend()
    figure.tight_layout()
    figure.savefig(DESTINATION / "training_loss.png")
    (DESTINATION / "training_loss_summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
