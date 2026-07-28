# MotionBricks — Game Animation Edition

> This branch removes the robot-control and hardware-deployment stacks from
> NVIDIA's GR00T Whole-Body Control repository and retains only the parts useful
> for game development, real-time character animation, and motion research.

[中文说明](README.md) · [MotionBricks documentation](motionbricks/README.md) ·
[Motion representation](motionbricks/docs/motion_representation.md)

## What This Branch Is

This is a focused MotionBricks workspace for studying and prototyping:

- real-time neural character motion generation;
- keyboard-driven locomotion and motion-style switching;
- root motion and articulated pose generation;
- motion tokenization with VQ-VAE;
- skeletal motion representations and coordinate conversions;
- motion retargeting and custom animation datasets;
- MuJoCo-based interactive animation preview.

MuJoCo and the existing G1 skeleton are retained as the preview runtime and the
reference skeleton required by the released checkpoints. They do not imply that
this branch contains robot deployment support.

## What Was Removed

The following robot-specific systems were intentionally removed:

- GEAR-SONIC reinforcement-learning training and evaluation;
- Decoupled Whole-Body Control;
- Unitree SDKs, DDS communication, motor control, and hardware safety;
- TensorRT robot deployment;
- VR robot teleoperation and VLA data collection/inference;
- camera, ROS, JetPack, systemd, Docker, and real-robot installation stacks;
- robot-only documentation, media, and third-party binaries.

The repository's original history remains available on the `main` branch.

## Project Layout

```text
motionbricks/
├── assets/                 # Preview images, G1 skeleton and meshes
├── docs/                   # Motion representation and dataset guides
├── motionbricks/
│   ├── data/               # Synthetic training data
│   ├── geometry/           # Rotation and quaternion utilities
│   ├── motion_backbone/    # Pose/root generation and interactive control
│   ├── motionlib/          # Skeleton and motion representations
│   └── vqvae/              # Motion tokenizer
├── out/                    # Released configs/checkpoints (Git LFS)
├── scripts/                # Demo and training entry points
└── setup.py
```

## Quick Start

Requirements: Python 3.10+, a CUDA-capable GPU, and Git LFS.

```bash
git lfs install
git lfs pull --include="motionbricks/out/**" --exclude=""
git lfs pull --include="motionbricks/assets/skeletons/g1/meshes/**" --exclude=""

cd motionbricks
conda create -n motionbricks python=3.10 -y
conda activate motionbricks
pip install -e .
python scripts/interactive_demo_g1.py
```

The demo uses `W`, `A`, `S`, and `D` for camera-relative locomotion. Additional
keys select styles such as stealth, injured, zombie, crawling, and dancing.
See [the MotionBricks guide](motionbricks/README.md) for the complete controls.

## Training Entry Points

```bash
cd motionbricks
python scripts/train_vqvae.py
python scripts/train_pose.py
python scripts/train_root.py
```

These scripts default to synthetic data so the training pipeline can be tested
without downloading a motion-capture dataset.

## Scope and Attribution

This branch is a derived, game-development-focused organization of the upstream
GR00T Whole-Body Control repository. MotionBricks authorship, citations, model
terms, and attribution remain as documented in
[motionbricks/README.md](motionbricks/README.md), [CITATION.cff](CITATION.cff),
and [LICENSE](LICENSE).
