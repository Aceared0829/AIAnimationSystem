"""Read-only P0 audit of same-Root cross-split families and explicit stance clips."""

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = Path(r"E:\AIAnimationSystemData\prepared\reference_guided_root_pose_v1_20260924_audited\contract.json")
REPORT_PATH = ROOT / "output/conditioned_data_audit_20260924_complete/report.json"
QUEUE_PATH = REPORT_PATH.parent / "review_queue.json"
DECISIONS_PATH = Path(r"D:\MotionDataLibrary\reviews\decisions.sqlite3")
OUT = Path(__file__).resolve().parent

FAMILY_IDS = [
    "aim_offset_and_static_pose_shared_root",
    "stand_crouch_transition",
    "relaxed_crouch_loop_left_variants",
    "idle_turn_and_ragdoll_reach_shared_root",
    "relaxed_idle_and_look_at_poi",
    "ragdoll_shove_direction_variants",
    "jump_backward_start_left_style_variants",
    "jump_backward_start_off_right_style_variants",
    "jump_lateral_start_off_left_duplicate",
    "relaxed_walk_loop_and_look_at_poi",
    "relaxed_static_pose_variants",
    "relaxed_run_start_left_right",
    "relaxed_slide_loop_variants",
]
STANCE_INDICES = (226, 227, 429, 430)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    source = Path(contract["source_dataset"])
    clips = contract["clips"]
    groups = report["identical_root_track_cross_split_examples"]
    assert len(groups) == len(FAMILY_IDS) == 13
    raw_cache = {}

    def load(index):
        if index not in raw_cache:
            clip = clips[index]
            path = source / clip["raw_file"]
            if sha256(path) != clip["raw_sha256"]:
                raise ValueError(f"SHA mismatch: {index}")
            with np.load(path, allow_pickle=False) as data:
                raw_cache[index] = {
                    "positions": data["positions"],
                    "root_track": data["root_track"],
                }
        return raw_cache[index]

    pair_rows = []
    family_rows = []
    for group_number, (family_id, indices) in enumerate(zip(FAMILY_IDS, groups), 1):
        active = [i for i in indices if not clips[i]["excluded_from_conditioned_dataset"]]
        comparable = []
        for left_pos, left in enumerate(indices):
            for right in indices[left_pos + 1 :]:
                a, b = clips[left], clips[right]
                if a["split"] == b["split"] or a["source_frames"] != b["source_frames"]:
                    continue
                ar, br = load(left), load(right)
                if not np.array_equal(ar["root_track"], br["root_track"]):
                    raise ValueError(f"Expected same Root: {left}, {right}")
                distances = np.linalg.norm(ar["positions"] - br["positions"], axis=-1) * 100
                row = {
                    "family_id": family_id,
                    "left_index": left,
                    "left_split": a["split"],
                    "left_asset": a["asset"].split("/")[-1].split(".")[0],
                    "right_index": right,
                    "right_split": b["split"],
                    "right_asset": b["asset"].split("/")[-1].split(".")[0],
                    "frames": a["source_frames"],
                    "active_both": not (a["excluded_from_conditioned_dataset"] or b["excluded_from_conditioned_dataset"]),
                    "mean_joint_distance_cm": round(float(distances.mean()), 6),
                    "max_joint_distance_cm": round(float(distances.max()), 6),
                }
                pair_rows.append(row)
                if row["active_both"]:
                    comparable.append(row)
        nearest = min(comparable, key=lambda row: row["mean_joint_distance_cm"], default=None)
        family_rows.append({
            "family_id": family_id,
            "group_number": group_number,
            "all_indices": ";".join(map(str, indices)),
            "active_indices": ";".join(map(str, active)),
            "splits": ";".join(sorted({clips[i]["split"] for i in active})),
            "categories": ";".join(sorted({clips[i]["category"] for i in active})),
            "active_windows": sum(clips[i]["windows"] for i in active),
            "active_comparable_cross_split_pairs": len(comparable),
            "nearest_pair_indices": "" if nearest is None else f'{nearest["left_index"]};{nearest["right_index"]}',
            "nearest_mean_joint_distance_cm": "" if nearest is None else nearest["mean_joint_distance_cm"],
            "assessment": (
                "exact_duplicate_already_excluded" if len({clips[i]["split"] for i in active}) == 1
                else "no_generation_windows" if not sum(clips[i]["windows"] for i in active)
                else "confirmed_near_duplicate_review_split" if nearest and nearest["mean_joint_distance_cm"] <= 2
                else "review_semantic_family_before_resplit"
            ),
        })

    history = contract["window"]["history_frames"]
    future = contract["window"]["future_frames"]
    stride = contract["window"]["stride_frames"]
    stance_rows = []
    stance_clips = []
    for index in STANCE_INDICES:
        clip = clips[index]
        raw = load(index)
        pelvis_y = raw["positions"][:, 0, 1] + raw["root_track"][:, 1]
        change = float(pelvis_y[-1] - pelvis_y[0])
        progress = (pelvis_y - pelvis_y[0]) / change
        phase_10 = int(np.flatnonzero(progress >= 0.1)[0])
        phase_90 = int(np.flatnonzero(progress >= 0.9)[0])
        last = clip["source_frames"] - history - future
        starts = list(range(0, last + 1, stride))
        if starts[-1] != last:
            starts.append(last)
        for start in starts:
            segment = pelvis_y[start + history : start + history + future]
            stance_rows.append({
                "clip_index": index,
                "split": clip["split"],
                "history_start_frame": start,
                "future_start_frame": start + history,
                "future_end_frame_inclusive": start + history + future - 1,
                "future_pelvis_height_span_cm": round(float(np.ptp(segment) * 100), 6),
            })
        stance_clips.append({
            "clip_index": index,
            "asset": clip["asset"],
            "split": clip["split"],
            "raw_sha256": clip["raw_sha256"],
            "frames": clip["source_frames"],
            "root_position_unique_count": int(len(np.unique(raw["root_track"][:, :3], axis=0))),
            "pelvis_height_change_cm": round(change * 100, 6),
            "pelvis_height_phase_10_to_90_frames_inclusive": [phase_10, phase_90],
            "window_count": len(starts),
            "max_future_pelvis_height_span_cm": round(max(row["future_pelvis_height_span_cm"] for row in stance_rows if row["clip_index"] == index), 6),
        })

    with (OUT / "stance_windows.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=stance_rows[0].keys())
        writer.writeheader()
        writer.writerows(stance_rows)
    (OUT / "stance_clips.json").write_text(json.dumps(stance_clips, indent=2) + "\n", encoding="utf-8")

    with (OUT / "same_root_cross_split_pairs.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=pair_rows[0].keys())
        writer.writeheader()
        writer.writerows(pair_rows)
    with (OUT / "source_family_draft.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=family_rows[0].keys())
        writer.writeheader()
        writer.writerows(family_rows)

    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    queue_sha = sha256(QUEUE_PATH)
    with sqlite3.connect(f"file:{DECISIONS_PATH.as_posix()}?mode=ro", uri=True) as db:
        decisions = {(cohort, int(index)): (status, note, updated)
                     for cohort, index, status, note, updated in db.execute(
                         "SELECT cohort,id,status,note,updated FROM decisions WHERE cohort LIKE 'conditioned_%'")}
    review_rows = []
    for row_number, item in enumerate(queue):
        page = row_number // 50 + 1
        cohort = f"conditioned_{queue_sha[:16]}_p{page:02}.json"
        status, note, updated = decisions.get((cohort, item["clip_index"]), ("unreviewed", "", ""))
        evidence = "bulk_mark_no_individual_view_claim" if "批量通过" in note else "individual_mark_no_detailed_note" if status == "approved" and not note.strip() else "has_note" if note.strip() else "none"
        review_rows.append({
            "clip_index": item["clip_index"],
            "cohort": cohort,
            "asset": item["asset"],
            "category": item["category"],
            "split": item["split"],
            "flags": ";".join(item["flags"]),
            "stored_status": status,
            "decision_evidence": evidence,
            "updated_utc": updated,
            "p0_followup": "full_playback_and_scene_root_review" if evidence == "bulk_mark_no_individual_view_claim" else "confirm_viewing_and_add_specific_note" if evidence == "individual_mark_no_detailed_note" else "inspect",
        })
    with (OUT / "review_queue_state.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=review_rows[0].keys())
        writer.writeheader()
        writer.writerows(review_rows)

    result = {
        "contract_sha256": sha256(CONTRACT_PATH),
        "audit_report_sha256": sha256(REPORT_PATH),
        "family_groups": len(family_rows),
        "active_comparable_cross_split_pairs": sum(r["active_both"] for r in pair_rows),
        "mean_joint_distance_cm_le": {
            str(t): sum(r["active_both"] and r["mean_joint_distance_cm"] <= t for r in pair_rows)
            for t in (1, 2, 3, 5)
        },
        "family_assessments": dict(Counter(r["assessment"] for r in family_rows)),
        "excluded_train_indices": contract["excluded_train_clip_indices"],
        "review_queue_sha256": queue_sha,
        "review_queue_count": len(review_rows),
        "review_decision_evidence_counts": dict(Counter(r["decision_evidence"] for r in review_rows)),
        "stance_windows_total": len(stance_rows),
        "stance_windows_with_future_pelvis_span_ge_10_cm": sum(r["future_pelvis_height_span_cm"] >= 10 for r in stance_rows),
    }
    (OUT / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
