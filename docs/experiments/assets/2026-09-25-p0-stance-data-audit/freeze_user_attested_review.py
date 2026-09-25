"""Freeze the existing Motion Review decisions and a separate user attestation."""

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
QUEUE = ROOT / "output/conditioned_data_audit_20260924_complete/review_queue.json"
DATABASE = Path(r"D:\MotionDataLibrary\reviews\decisions.sqlite3")
OUTPUT = Path(__file__).resolve().parent / "restart_2026-09-25"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attested-at-utc", required=True)
    args = parser.parse_args()

    queue_bytes = QUEUE.read_bytes()
    queue = json.loads(queue_bytes)
    queue_sha = sha256(queue_bytes)
    if len(queue) != 107 or len({item["clip_index"] for item in queue}) != 107:
        raise ValueError("Expected exactly 107 unique queued clips")

    rows = []
    decision_records = []
    with sqlite3.connect(f"file:{DATABASE.as_posix()}?mode=ro", uri=True) as db:
        for index, item in enumerate(queue):
            cohort = f"conditioned_{queue_sha[:16]}_p{index // 50 + 1:02}.json"
            decision = db.execute(
                "SELECT status,note,updated FROM decisions WHERE cohort=? AND id=?",
                (cohort, str(item["clip_index"])),
            ).fetchone()
            if decision is None or decision[0] != "approved":
                raise ValueError(f"Clip {item['clip_index']} is not approved in {cohort}")
            status, note, updated = decision
            note = note or ""
            legacy_method = "bulk_marker" if "批量通过" in note else "single_mark"
            rows.append({
                "queue_position": index + 1,
                "clip_index": item["clip_index"],
                "asset": item["asset"],
                "cohort": cohort,
                "stored_status": status,
                "stored_updated_utc": updated,
                "legacy_mark_method": legacy_method,
                "user_directed_per_clip_status": "approved",
            })
            decision_records.append([cohort, str(item["clip_index"]), status, note, updated])

    OUTPUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT / "review_acceptance.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    result = {
        "attested_at_utc": args.attested_at_utc,
        "attestation_source": "user message in the current Codex task",
        "user_statement": "这107段动作是全验收通过的，就当我是一个一个全部标记了",
        "meaning": "User directs treating all 107 queued clips as individually approved decisions.",
        "assistant_observation": "The agent verified stored approvals and data identities; it did not witness 107 individual playbacks.",
        "review_queue_sha256": queue_sha,
        "queue_count": len(rows),
        "stored_status_counts": dict(Counter(row["stored_status"] for row in rows)),
        "legacy_mark_method_counts": dict(Counter(row["legacy_mark_method"] for row in rows)),
        "decision_records_sha256": sha256(json.dumps(decision_records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
        "review_acceptance_csv_sha256": sha256(csv_path.read_bytes()),
        "sqlite_modified": False,
    }
    (OUTPUT / "review_attestation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
