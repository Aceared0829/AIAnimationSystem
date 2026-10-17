"""给已生成的观察样本关联来源整段/分段语义，建立新的审核身份。"""

import argparse
import csv
import json
import re
import shutil
from pathlib import Path

from data.tools.native_review_store import load_native_review_inputs
from data.tools.soma_observation import sha, write_json


def temporal_reading(record, duration):
    events = record["events"]
    if record["num_events"] != len(events):
        raise ValueError("分段事件数量不匹配")
    previous_end = 0.0
    gaps, outside = [], []
    for index, event in enumerate(events):
        start, end = event["start_time"], event["end_time"]
        if not 0 <= start < end or start < previous_end - 1e-6:
            raise ValueError("来源事件时序无效或重叠")
        if start > previous_end + 1e-6:
            gaps.append([previous_end, start])
        if end > duration + 1e-6:
            outside.append({"event": index, "end_beyond_motion_s": end - duration})
        previous_end = end
    if previous_end < duration - 1e-6:
        gaps.append([previous_end, duration])
    return {"events": events, "gaps_s": gaps, "ends_beyond_motion": outside,
            "clock_status": "source_seconds_alignment_unverified", "contact_truth": "unknown",
            "note": "来源为v002分段文本，动作元数据为v004；按文件名关联，版本兼容与时间对齐待确认。原始秒数不裁剪、不伸缩；页面跳转仅按同起点秒数近似定位。"}


def enrich(root, index, run_id, readings):
    root, index = Path(root).resolve(), Path(index).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id):
        raise ValueError("无效run_id")
    index, entries, _ = load_native_review_inputs(index, root)
    selection = json.loads((index.parent / "selection.json").read_text(encoding="utf-8"))
    metadata = root / "metadata/seed_metadata_v004.csv"
    if sha(metadata) != selection["metadata_sha256"]:
        raise ValueError("元数据已改变，需要重新核对观察样本")
    by_source = {e["asset"]: e for e in entries}
    rows = {}
    with metadata.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            source = row["move_soma_uniform_path"].replace("\\", "/")
            if source in by_source:
                if source in rows:
                    raise ValueError("来源元数据关联不唯一")
                rows[source] = row
    if len(rows) != len(entries):
        raise ValueError("元数据未覆盖观察样本")
    wanted = {row["filename"] for row in rows.values()}
    temporal_file = root / "metadata/seed_metadata_v002_temporal_labels.jsonl"
    temporal = {}
    with temporal_file.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record["filename"] in wanted:
                if record["filename"] in temporal:
                    raise ValueError("分段语义关联不唯一")
                temporal[record["filename"]] = record
    reading = json.loads(Path(readings).read_text(encoding="utf-8"))
    destination = index.parent.parent / run_id
    destination.mkdir(exist_ok=False)
    source_report = json.loads((index.parent / "run.json").read_text(encoding="utf-8"))
    records = {r["source_id"]: r for r in source_report["results"]}
    summaries, output_records = [], []
    for entry in entries:
        row = rows[entry["asset"]]
        record = dict(records[entry["asset"]])
        original = Path(record["observation"])
        if sha(original) != record["observation_sha256"]:
            raise ValueError("观察标注哈希不一致")
        observation = json.loads(original.read_text(encoding="utf-8"))
        observation["labels"] = {key: value for key, value in row.items() if key.startswith("content_") or key in {"package", "category"}}
        name = row["filename"]
        semantics = {"summary_zh": reading["summaries"][name], "issues": reading["issues"].get(name, []),
                     "status": "source_text_reading_not_visual_acceptance", "filename": name,
                     "temporal": temporal_reading(temporal[name], (entry["frames"] - 1) / entry["fps"]) if name in temporal else None}
        observation["semantic_reading"] = semantics
        output = destination / original.name
        write_json(output, observation)
        record.update(observation=str(output), observation_sha256=sha(output))
        output_records.append(record)
        summaries.append({"filename": name, "summary_zh": semantics["summary_zh"], "issues": semantics["issues"],
                          "hips_vertical_displacement_m": observation["metrics"]["hips_displacement_m"][1],
                          "temporal": semantics["temporal"], "source_labels": observation["labels"]})
    write_json(destination / "run.json", dict(source_report, scope="semantic_observation_no_motion_changes", results=output_records))
    shutil.copyfile(index, destination / index.name)
    acceptance = json.loads((index.parent / "acceptance.json").read_text(encoding="utf-8"))
    write_json(destination / "acceptance.json", dict(acceptance, batches=[run_id], scope="source_readback_inherited_semantics_unreviewed"))
    write_json(destination / "semantic-report.json", {"source_index": str(index), "source_index_sha256": sha(index),
               "metadata_sha256": sha(metadata), "temporal_sha256": sha(temporal_file), "readings_sha256": sha(readings),
               "matched_clips": len(entries), "temporal_matched": sum(s["temporal"] is not None for s in summaries),
               "clips": summaries})
    text = ["# SOMA 30条观察样本的来源语义核对", "", "中文释义是对来源文本的阅读，不代表逐帧验收。原始字段不修改。", "",
            "v004整段元数据与v002分段说明按完整filename关联；不把文件名角度编码或布尔标签直接当物理真值。", ""]
    for clip in summaries:
        text += [f"## {clip['filename']}", "", clip["summary_zh"], "",
                 f"骨盆净垂直位移：{clip['hips_vertical_displacement_m']:.3f} m（仅作运动证据，不是Actor Root）。", ""]
        text += [f"- 待核对：{issue}" for issue in clip["issues"]]
        text += ["", "来源原文：", ""]
        for key, value in clip["source_labels"].items():
            text.append(f"- {key}：{value}")
        text += ["", "分段说明（原始秒数；时间对齐待验证）：", ""]
        if clip["temporal"]:
            text += [f"- {e['start_time']:.6f}–{e['end_time']:.6f}s：{e['description']}" for e in clip["temporal"]["events"]]
    (destination / "semantic-report.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return destination / index.name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("E:/MotionWeaverData"))
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--readings", type=Path, default=Path(__file__).parents[1] / "annotations/soma_observation_semantics_v1.json")
    args = parser.parse_args()
    print(enrich(args.data_root, args.index, args.run_id, args.readings))


if __name__ == "__main__":
    main()
