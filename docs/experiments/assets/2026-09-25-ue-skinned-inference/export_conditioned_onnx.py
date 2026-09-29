"""Export the selected no-reference conditioned checkpoint for an isolated UE test."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from training.pretrain.train_conditioned_pose import ReferenceGuidedPose


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)

    saved = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model = ReferenceGuidedPose(79, saved["config"]["width"])
    model.load_state_dict(saved["model"])
    model.eval()
    bones = model.features
    history = torch.zeros((1, 24, bones + 7), dtype=torch.float32)
    root_plan = torch.zeros((1, 24, 7), dtype=torch.float32)
    root_plan[..., 6] = 1.0
    reference = torch.zeros((1, 24, bones), dtype=torch.float32)
    mask = torch.zeros((1, 24, 1), dtype=torch.float32)
    path = args.output / "conditioned_pose.onnx"
    torch.onnx.export(model, (history, root_plan, reference, mask), path,
                      input_names=["history", "root_plan", "reference", "mask"],
                      output_names=["pose"], opset_version=18, dynamo=False,
                      do_constant_folding=True)
    onnx.checker.check_model(str(path))
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(20260925)
    fixtures = []
    for index in range(3):
        inputs = [history.numpy().copy(), root_plan.numpy().copy(),
                  reference.numpy().copy(), mask.numpy().copy()]
        if index:
            inputs[0] = rng.normal(0, 0.35, inputs[0].shape).astype(np.float32)
            inputs[1] = rng.normal(0, 0.2, inputs[1].shape).astype(np.float32)
            inputs[1][..., 6] = 1.0
        with torch.inference_mode():
            expected = model(*(torch.from_numpy(value) for value in inputs)).numpy()
        found, = session.run(None, dict(zip(("history", "root_plan", "reference", "mask"), inputs)))
        error = float(np.max(np.abs(expected - found)))
        fixtures.append({"index": index, "max_abs_error": error,
                         "finite": bool(np.isfinite(found).all())})
        if not np.isfinite(found).all() or error > 0.01:
            raise ValueError(f"ONNX mismatch for fixture {index}: {error}")
    report = {"checkpoint": str(args.checkpoint), "checkpoint_sha256": digest(args.checkpoint),
              "onnx_sha256": digest(path), "contract_sha256": saved["config"]["contract_sha256"],
              "format": "conditioned_pose_24x79_no_reference_v1",
              "inputs": {item.name: list(item.shape) for item in session.get_inputs()},
              "outputs": {item.name: list(item.shape) for item in session.get_outputs()},
              "opset": 18, "fixtures": fixtures, "torch": torch.__version__,
              "onnxruntime": ort.__version__}
    (args.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
