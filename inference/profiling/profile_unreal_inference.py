"""测量单流 FP32 神经网络推理，不包含 UE、上游 token 生成器或动画后处理。"""
import argparse
import gc
import json
from pathlib import Path
import numpy as np
import torch
from inference.export.export_unreal_inference import load_package
from motionbricks.helper.data_training_util import extract_feature_from_motion_rep


def main(args):
    torch.set_num_threads(4)
    if not torch.cuda.is_available():
        raise RuntimeError("该工具要求 CUDA，以 CUDA Event 测量 GPU 时间")
    results = []
    for folder in args.packages:
        net, rep = load_package(folder)
        metadata = json.loads((Path(folder) / "manifest.json").read_text(encoding="utf8"))
        motion = torch.from_numpy(np.load(args.motion))[:64][None]
        local = rep.dual_rep.global_to_local(motion, is_normalized=True, to_normalize=True, lengths=torch.tensor([motion.shape[1]]))
        net = net.cuda().eval()
        local = local.cuda()
        external = extract_feature_from_motion_rep(local, net.motion_rep, net.decoder_external_cond_feature_mode)
        if metadata["inference_mode"] == "decoder_only":
            # 有效的零号码，用于测资源；质量等价另用真实 token 验证。
            codes = torch.zeros((1, local.shape[1] // 4), dtype=torch.long, device="cuda")
            forward = lambda: net.forward_decoder(codes, target_cond=None, external_cond=external)
        else:
            forward = lambda: net(local, target_cond=None, external_cond=external)
        with torch.no_grad():
            for _ in range(5):
                forward()
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            timings = []
            for _ in range(30):
                start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                start.record()
                forward()
                end.record()
                end.synchronize()
                timings.append(start.elapsed_time(end))
        results.append({"package": str(Path(folder).resolve()), "mode": metadata["inference_mode"], "batch": 1, "frames": int(local.shape[1]),
                        "median_ms": float(np.median(timings)), "p95_ms": float(np.quantile(timings, .95)),
                        "peak_allocated_bytes": torch.cuda.max_memory_allocated(), "parameters": sum(p.numel() for p in net.parameters())})
        del forward, net, rep, local, external, motion
        if metadata["inference_mode"] == "decoder_only":
            del codes
        gc.collect()
        torch.cuda.empty_cache()
    report = {"gpu": torch.cuda.get_device_name(0), "precision": "FP32", "scope": "CUDA neural forward only; allocated tensor memory, not total application VRAM", "results": results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", nargs="+", required=True)
    parser.add_argument("--motion", required=True)
    parser.add_argument("--output", required=True)
    main(parser.parse_args())
