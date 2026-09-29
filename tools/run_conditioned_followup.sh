#!/usr/bin/env bash
set -euo pipefail

workspace="${1:-/workspace}"
code="$workspace/code"
release="$workspace/release"
source="$workspace/source"
lock="$code/data/freezes/reference_guided_root_pose_v1_20260924.json"
cd "$code"
export PYTHONPATH="$code${PYTHONPATH:+:$PYTHONPATH}"

python -m unittest discover -s tests -p 'test_conditioned_pose_training.py' -v

run_one() {
  local name="$1"
  shift
  local output="$workspace/runs/$name"
  if [[ -e "$output" ]]; then
    printf 'Refusing to overwrite %s\n' "$output" >&2
    return 1
  fi
  python -m training.pretrain.train_conditioned_pose \
    --release "$release" --lock "$lock" --source-override "$source" \
    --output "$output" --epochs 5 --batch-size 8 --width 256 --seed 42 "$@"
  python -m training.evaluation.evaluate_conditioned_quality \
    --checkpoint "$output/epoch_005.pt" --release "$release" --lock "$lock" \
    --source-override "$source" --split validation \
    --output "$output/validation_quality.json"
  sha256sum "$output/epoch_005.pt" "$output/validation_quality.json" \
    > "$output/artifact_sha256.txt"
}

run_one conditioned_opt_hybrid_v1 --reference-sampling hybrid
run_one conditioned_opt_contact_low_v1 --contact-weight 0.002
