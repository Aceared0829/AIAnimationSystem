"""Bind the 30 diagnostic contact candidates to the existing Motion Review UI."""

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--candidate-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    contract_path = args.contract / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    with args.candidate_csv.open(newline="", encoding="utf-8-sig") as stream:
        candidates = list(csv.DictReader(stream))
    if len(candidates) != 30 or len({row["clip_index"] for row in candidates}) != 30:
        raise ValueError("expected 30 distinct diagnostic candidates")
    queue = []
    for row in candidates:
        index = int(row["clip_index"])
        clip = contract["clips"][index]
        if clip["asset"] != row["asset"] or clip["category"] != row["category"]:
            raise ValueError(f"candidate/contract mismatch at {index}")
        flags = ["contact_diagnostic_review"]
        if int(row["contact_pairs"]) <= 3:
            flags.append("sparse_center_contact_pairs")
        if float(row["local_floor_proxy_only_fraction"]) >= 0.10:
            flags.append("absolute_floor_height_disagreement")
        queue.append({"clip_index": index, "asset": clip["asset"],
                      "category": clip["category"], "split": clip["split"],
                      "frames": clip["source_frames"], "flags": flags,
                      "diagnostic_root_speed_mean_mps": float(row["root_speed_mean_mps"]),
                      "diagnostic_center_contact_pairs": int(row["contact_pairs"]),
                      "diagnostic_local_floor_proxy_only_fraction": float(row["local_floor_proxy_only_fraction"])})
    args.output.mkdir(parents=True)
    report = {"schema_version": 1, "audit_type": "contact_speed_diagnostic_review_v1",
              "contract_sha256": sha256(contract_path), "checked_clips": 1217,
              "review_queue_clips": len(queue),
              "source_candidate_csv_sha256": sha256(args.candidate_csv),
              "note": "Candidates for inspection only; no automatic approval or exclusion."}
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "review_queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"queue": len(queue), "contract_sha256": report["contract_sha256"]}))


if __name__ == "__main__":
    main()
