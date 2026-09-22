"""固定同一源区间比较导出包；只评估算法质量，不推断 UE GPU 性能。"""
import argparse
import json
from pathlib import Path
import numpy as np
import onnxruntime as ort
from inference.export.export_unreal_animgraph import pack_raw_pose
from inference.profiling.evaluate_unreal_streaming import localize, positions, simulate, metric, rms


def compare(baseline, candidate, dataset, output, selection="showcase"):
    dataset, output = Path(dataset), Path(output)
    skeleton = json.loads((dataset / "skeleton.json").read_text(encoding="utf8"))
    clips = json.loads((dataset / "dataset.json").read_text(encoding="utf8"))["clips"]
    parents = [bone["parent"] for bone in skeleton["bones"]]
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    bundles = {}
    for name, folder in (("baseline", baseline), ("candidate", candidate)):
        folder = Path(folder)
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf8"))
        bundles[name] = (manifest, ort.InferenceSession(str(folder / "model.onnx"), options, providers=["CPUExecutionProvider"]))
    first, second = bundles["baseline"][0], bundles["candidate"][0]
    for field in ("training_signature", "checkpoint_sha256", "fps", "bones"):
        if first[field] != second[field]:
            raise ValueError(f"对照包契约不一致：{field}")
    selected = [c for c in clips if c["split"] == "test"]
    if selection == "showcase":
        assets = {v["asset"] for v in first["validation"]}
        selected = [c for c in selected if c["asset"] in assets or c["labels"]["category"] == "Traversal"]
    start = max(m[0]["window_frames"] for m in bundles.values()) + 4
    report = {"completed": False, "scope": "same source times, 60 Hz playback, stride 4, delay 8; ONNX CPU quality only",
              "selection": selection, "source_start_frame": start, "bundles": {k: {f: v[0].get(f) for f in ("onnx_sha256", "window_frames", "pose_condition")} for k, v in bundles.items()},
              "clips": [], "skipped": []}
    for clip in selected:
        with np.load(dataset / clip["raw_file"]) as raw:
            packed = pack_raw_pose(raw, skeleton)
        if len(packed) - 8 - start < 10:
            report["skipped"].append({"asset": clip["asset"], "reason": "共同稳态区间不足 10 帧", "frames": len(packed)})
            continue
        source = localize(packed, parents)
        variants = {}
        for name, (manifest, session) in bundles.items():
            width = manifest["window_frames"]
            windows = {}
            for end in range(width - 1, len(packed), 4):
                sample = np.concatenate([packed[end-width+1:end+1], packed[end:end+1]])[None]
                windows[end] = localize(session.run(None, {"pose_history": sample})[0][0], parents)
            variants[name] = simulate(source, windows, 8, width)
            if name == "candidate":
                variants["candidate_residual"] = simulate(source, windows, 8, width, "source_residual")
        common = sorted(set(range(start, len(source)-8)).intersection(*(set(v) for v in variants.values())))
        if len(common) < 10 or np.any(np.diff(common) != 1):
            raise ValueError(f"共同区间不连续：{clip['asset']}")
        reference = source[common]
        reference_positions = positions(reference, parents)
        item = {"asset": clip["asset"], "category": clip["labels"]["category"], "samples": len(common),
                "source_interval": [common[0], common[-1]], "variants": {}}
        for name, frames in variants.items():
            values = np.stack([frames[i] for i in common])
            predicted = positions(values, parents)
            angle = 2*np.arccos(np.clip(np.abs(np.sum(values[..., 3:]*reference[..., 3:], axis=-1)), 0, 1))*180/np.pi
            item["variants"][name] = {
                "joint_rmse_cm": metric(rms(predicted-reference_positions)),
                "local_rotation_rmse_degrees": metric(np.sqrt(np.mean(angle**2, axis=-1))),
                "acceleration_cm_per_frame2": metric(rms(np.diff(predicted, n=2, axis=0))),
                "acceleration_error_cm_per_frame2": metric(rms(np.diff(predicted-reference_positions, n=2, axis=0))),
                "velocity_error_cm_per_frame": metric(rms(np.diff(predicted-reference_positions, axis=0)))}
        report["clips"].append(item)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps({"clip": len(report["clips"]), "category": item["category"], "rmse": {k: round(v["joint_rmse_cm"]["mean"], 3) for k,v in item["variants"].items()}}), flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    report["completed"] = True
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--selection", choices=("showcase", "test"), default="showcase")
    args = parser.parse_args()
    compare(args.baseline, args.candidate, args.dataset, args.output, args.selection)
