"""只读量化旁路诊断，不改权重；旁路结果不是可部署模型或连续自编码器上限。"""
import argparse
import json
from pathlib import Path
from collections import defaultdict
import numpy as np
import torch
from training.evaluation.evaluate_native_quality import decode_raw, measure
from training.evaluation.evaluate_unreal_vqvae import load_vqvae


def main(args):
    torch.set_num_threads(4)
    folder = Path(args.dataset)
    data = json.loads((folder / "dataset.json").read_text(encoding="utf8"))
    net, rep, contract = load_vqvae(args.checkpoint)
    if data["training_signature"] != contract["signature"]:
        raise ValueError("数据契约不匹配")
    groups = defaultdict(list)
    for item in data["clips"]:
        if item["split"] == "validation":
            groups[item["labels"]["category"]].append(item)
    results = []
    for category, items in sorted(groups.items()):
        for index in np.unique(np.linspace(0, len(items) - 1, min(2, len(items)), dtype=int)):
            item = items[index]
            with np.load(folder / item["raw_file"]) as z:
                raw = {key: z[key] for key in z.files}
            ref, quant, _, _, _ = decode_raw(net, rep, raw)
            _, continuous, _, _, _ = decode_raw(net, rep, raw, bypass_quantizer=True)
            results.append({"asset": item["asset"], "category": category, "quantized": measure(ref, quant), "bypassed": measure(ref, continuous)})
    report = {"checkpoint": str(Path(args.checkpoint).resolve()), "split": "validation", "sample_count": len(results),
              "parameters": sum(p.numel() for p in net.parameters()),
              "components": {name: sum(p.numel() for p in module.parameters()) for name, module in [("encoder", net.encoder), ("decoder", net.decoder), ("quantizer", net.quantizer)]},
              "state_bytes": sum(t.numel() * t.element_size() for t in net.state_dict().values()),
              "mean_pose_cm": {key: float(np.mean([r[key]["pose_rmse_cm"] for r in results])) for key in ("quantized", "bypassed")},
              "limitations": "旁路的连续隐变量可能偏离解码器训练分布；不能把差值等同于量化独立贡献，也不是训练过的连续自编码器对照。", "samples": results}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    main(parser.parse_args())
