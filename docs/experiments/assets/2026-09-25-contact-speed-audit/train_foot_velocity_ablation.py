"""Matched continuation: existing loss versus world-foot-velocity trajectory loss.

Both arms start at the same selected checkpoint, consume the same train clips and
window sequence, and use generated-history feedback. This never edits the release.
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs/experiments/assets/2026-09-25-closed-loop-optimization"))
from train_rollout_ablation import ThreeWindowClips, orthogonal_first_two, sha256  # noqa: E402
from training.pretrain.train_conditioned_pose import (ReferenceGuidedPose, losses,  # noqa: E402
                                                     root_world_positions, verify_release)


RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
INITIAL = Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02"
               r"\generated_contact\epoch_010.pt")


def one_epoch(model, loader, optimizer, mean, std, feet, *, arm, epoch, seed,
              contact_weight, foot_velocity_weight):
    model.train()
    total = np.zeros(4, dtype=np.float64)
    generator = torch.Generator(device="cuda").manual_seed(seed + epoch * 1000003)
    started = time.monotonic()
    for step, parts in enumerate(loader, 1):
        h0, r1, h1_true, r2, target, contacts = [part.to("cuda", non_blocking=True) for part in parts]
        reference = torch.zeros((len(h0), 24, model.features), device="cuda")
        mask = torch.zeros((len(h0), 24, 1), device="cuda")
        model.eval()
        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            first = model(h0, r1, reference, mask).float().reshape(len(h0), 24, model.bones, 9)
        model.train()
        first = torch.cat((first[..., :3], orthogonal_first_two(first[..., 3:])), dim=-1)
        generated = torch.cat((first.reshape(len(h0), 24, -1), h1_true[..., -7:]), dim=-1)
        use_generated = torch.rand((len(h0), 1, 1), generator=generator, device="cuda") < 0.75
        history = torch.where(use_generated, generated, h1_true)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            prediction = model(history, r2, reference, mask).float()
            base, position, rotation = losses(prediction, target, mask, std,
                                              pose_mean=mean, root_plan=r2, contacts=contacts,
                                              foot_indices=feet, contact_weight=contact_weight)
            pred_pose = prediction.reshape(len(h0), 24, model.bones, 9)[..., :3] * std + mean
            target_pose = target.reshape(len(h0), 24, model.bones, 9)[..., :3] * std + mean
            pred_world = root_world_positions(pred_pose[:, :, feet], r2)
            target_world = root_world_positions(target_pose[:, :, feet], r2)
            pred_velocity = torch.diff(pred_world, dim=1) * 30
            target_velocity = torch.diff(target_world, dim=1) * 30
            trajectory = F.smooth_l1_loss(pred_velocity, target_velocity, beta=0.5)
            loss = base + (foot_velocity_weight * trajectory if arm == "foot_velocity" else 0.0)
        if not torch.isfinite(loss):
            raise ValueError(f"nonfinite loss: {arm}, epoch {epoch + 1}, step {step}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total += np.array((loss.item(), position.item(), rotation.item(), trajectory.item())) * len(h0)
        if step % 30 == 0 or step == len(loader):
            print(f"{arm} epoch={epoch + 1} step={step}/{len(loader)} elapsed_s={time.monotonic()-started:.1f}",
                  flush=True)
    return {"epoch": epoch + 1, "loss": float(total[0] / len(loader.dataset)),
            "pose_axis_rmse_cm": float(np.sqrt(total[1] / len(loader.dataset)) * 100),
            "rotation_6d_mse": float(total[2] / len(loader.dataset)),
            "foot_velocity_smooth_l1_mps": float(total[3] / len(loader.dataset)),
            "seconds": time.monotonic() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initial", type=Path, default=INITIAL)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--max-clips", type=int)
    parser.add_argument("--contact-weight", type=float, default=0.0005)
    parser.add_argument("--foot-velocity-weight", type=float, default=0.01)
    args = parser.parse_args()
    if args.output.exists() or min(args.epochs, args.batch_size) < 1:
        parser.error("new output directory and positive counts required")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required")
    contract, lock = verify_release(RELEASE, LOCK)
    initial = torch.load(args.initial, map_location="cpu", weights_only=False)
    if initial["config"]["contract_sha256"] != lock["artifacts_sha256"]["contract/contract.json"]:
        raise ValueError("checkpoint/frozen release mismatch")
    stats = contract["stats"]["pose_m"]
    mean_np = np.load(RELEASE / "contract/stats" / stats["mean"]).astype(np.float32)
    std_np = np.load(RELEASE / "contract/stats" / stats["std"]).astype(np.float32)
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in
            ("left_foot", "left_toe", "right_foot", "right_toe")]
    dataset = ThreeWindowClips(contract, mean_np, std_np, seed=args.seed, max_clips=args.max_clips)
    mean, std = torch.from_numpy(mean_np).to("cuda"), torch.from_numpy(std_np).to("cuda")
    config = {"contract_sha256": initial["config"]["contract_sha256"],
              "source_manifest_sha256": contract["source_manifest_sha256"],
              "initial_checkpoint": str(args.initial.resolve()), "initial_checkpoint_sha256": sha256(args.initial),
              "train_clips": len(dataset), "clip_indices": [row[0] for row in dataset.clips],
              "epochs": args.epochs, "batch_size": args.batch_size, "lr": args.lr, "seed": args.seed,
              "generated_history_probability": 0.75, "contact_weight": args.contact_weight,
              "foot_velocity_weight": args.foot_velocity_weight,
              "trajectory_loss": "SmoothL1(beta=0.5 m/s) on world-foot velocity vector, all future frame pairs",
              "root_condition": "source future Root, no future pose reference",
              "device": torch.cuda.get_device_name(0), "torch": torch.__version__}
    args.output.mkdir(parents=True)
    (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    for arm in ("control", "foot_velocity"):
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        random.seed(args.seed)
        model = ReferenceGuidedPose(contract["bone_count"], initial["config"]["width"]).to("cuda")
        model.load_state_dict(initial["model"])
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
        loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=0,
                            pin_memory=True, generator=torch.Generator().manual_seed(args.seed))
        folder = args.output / arm
        folder.mkdir()
        metrics = []
        for epoch in range(args.epochs):
            dataset.epoch = epoch
            result = one_epoch(model, loader, optimizer, mean, std, feet, arm=arm, epoch=epoch,
                               seed=args.seed, contact_weight=args.contact_weight,
                               foot_velocity_weight=args.foot_velocity_weight)
            metrics.append(result)
            checkpoint_config = dict(initial["config"], experiment="world_foot_velocity_ablation",
                                     arm=arm, fine_tune_config=config,
                                     initial_checkpoint=str(args.initial.resolve()),
                                     fine_tune_epoch=epoch + 1)
            torch.save({"model": model.state_dict(), "config": checkpoint_config,
                        "epoch": epoch + 1, "metrics": result}, folder / f"epoch_{epoch + 1:03}.pt")
            print(json.dumps({"arm": arm, **result}), flush=True)
        (folder / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        del model, optimizer, loader
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
