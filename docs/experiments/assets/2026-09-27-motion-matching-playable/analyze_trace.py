"""Summarize real CMC and skinned foot motion from the plugin player test."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path


def analyze(path: Path) -> dict:
    data = path.read_bytes()
    rows = list(csv.DictReader(data.decode("utf-8-sig").splitlines()))
    modes = []
    for mode in (0, 1, 2):
        standing = [
            row for row in rows
            if int(row["mode"]) == mode and int(row["crouch"]) == 0
        ]
        if not standing:
            continue
        started = float(standing[0]["time_s"])
        settled = [
            row for row in standing
            if float(row["time_s"]) >= started + 0.5
        ]
        foot_speeds = []
        for left, right in zip(rows, rows[1:]):
            if int(left["mode"]) != mode or int(right["mode"]) != mode:
                continue
            if int(left["crouch"]) or int(right["crouch"]):
                continue
            if float(left["time_s"]) < started + 0.5:
                continue
            dt = float(right["time_s"]) - float(left["time_s"])
            if not 0.02 <= dt <= 0.08:
                continue
            for foot in ("foot_l", "foot_r"):
                if max(float(left[f"{foot}_z_cm"]), float(right[f"{foot}_z_cm"])) > 18.0:
                    continue
                dx = float(right[f"{foot}_x_cm"]) - float(left[f"{foot}_x_cm"])
                dy = float(right[f"{foot}_y_cm"]) - float(left[f"{foot}_y_cm"])
                foot_speeds.append(math.hypot(dx, dy) / dt / 100.0)
        modes.append({
            "mode": mode,
            "standing_samples": len(standing),
            "settled_samples": len(settled),
            "mean_cmc_speed_mps": statistics.mean(float(row["speed_cmps"]) for row in settled) / 100.0,
            "low_foot_height_threshold_cm": 18.0,
            "low_foot_speed_sample_count": len(foot_speeds),
            "low_foot_speed_median_mps": statistics.median(foot_speeds) if foot_speeds else None,
            "low_foot_speed_mean_mps": statistics.mean(foot_speeds) if foot_speeds else None,
            "foot_local_x_range_cm": {
                foot: max(float(row[f"{foot}_x_cm"]) - float(row["actor_x_cm"]) for row in settled)
                - min(float(row[f"{foot}_x_cm"]) - float(row["actor_x_cm"]) for row in settled)
                for foot in ("foot_l", "foot_r")
            },
        })
    return {
        "trace": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "rows": len(rows),
        "modes": modes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = [analyze(path) for path in args.traces]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
