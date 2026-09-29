#!/usr/bin/env bash
set -euo pipefail

# 解包后的同一封版契约贯穿数据校验、训练、测试评估和推理验收。
workspace="${1:-/workspace}"
code="$workspace/code"
source="$workspace/source"
release="$workspace/release"
run="$workspace/runs/conditioned_pose_remote_20260924"
lock="$code/data/freezes/reference_guided_root_pose_v1_20260924.json"

cd "$code"
export PYTHONPATH="$code${PYTHONPATH:+:$PYTHONPATH}"
# 精简代码包不包含上游 setup.py 声明的空兼容目录；补齐后安装模块映射。
for package_dir in training/models/vqvae training/models/backbone inference/runtime/backbone inference/demo inference/runtime/experiment; do
  mkdir -p "$code/$package_dir"
done
python -m pip install --no-deps -e "$code"
python -m unittest discover -s tests -p 'test_conditioned_pose_training.py' -v
python -m training.pretrain.train_conditioned_pose \
  --release "$release" --lock "$lock" --source-override "$source" \
  --output "$run" --epochs 5 --batch-size 8 --width 256 --seed 42
python -m training.evaluation.evaluate_conditioned_pose \
  --checkpoint "$run/epoch_005.pt" --release "$release" --lock "$lock" \
  --source-override "$source" --baseline "$release/baseline/report.json" \
  --output "$run/test_evaluation.json"
python -m inference.runtime.conditioned_pose \
  --checkpoint "$run/epoch_005.pt" --release "$release" --lock "$lock" \
  --source-override "$source" --output "$run/test_inference_smoke.npz"
sha256sum "$run/epoch_005.pt" "$run/test_evaluation.json" "$run/test_inference_smoke.npz" \
  > "$run/artifact_sha256.txt"
