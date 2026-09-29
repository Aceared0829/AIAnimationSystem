"""Matched pilot: original labels, toe-witness targets, and speed/phase sampling.

All arms start from the same checkpoint, use the same architecture, optimizer,
batch count and frozen train split. No source motion or frozen labels are edited.
"""

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs/experiments/assets/2026-09-25-closed-loop-optimization"))
from train_rollout_ablation import ThreeWindowClips, orthogonal_first_two  # noqa: E402
from training.pretrain.train_conditioned_pose import (ReferenceGuidedPose, losses,  # noqa: E402
                                                     verify_release)
from data.runtime.conditioned_motion import root_local  # noqa: E402
from contact_v2_audit import contact_candidates  # noqa: E402


RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
INITIAL = Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02"
               r"\generated_contact\epoch_010.pt")
ARMS = ("control", "toe_witness", "speed_phase")
ROLES = ("left_foot", "left_toe", "right_foot", "right_toe")
SPEED_BINS = (("0-0.2", .2), ("0.2-1", 1.), ("1-2", 2.), ("2-4", 4.), ("4+", float("inf")))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def speed_bin(value):
    return next(name for name, upper in SPEED_BINS if value < upper)


class PilotClips(ThreeWindowClips):
    def __init__(self, contract, mean, std, feet, *, seed, max_clips=None):
        super().__init__(contract, mean, std, seed=seed, max_clips=max_clips)
        self.feet = feet
        self.arm = "control"
        self.v2 = {}
        self.groups = []
        self.group_counts = Counter()
        manifest = json.loads((Path(contract["source_dataset"]) / "dataset.json").read_text(encoding="utf-8"))
        self.added_bits = Counter()
        for index, combined, roots, original in self.clips:
            values = combined.reshape(len(combined), contract["bone_count"], 9)
            positions = values[..., :3] * std + mean
            weights, added, _, _, _ = contact_candidates(
                positions, roots, feet, original.astype(bool), contract["fps"])
            self.v2[index] = weights
            self.added_bits[contract["clips"][index]["category"]] += int(added.sum())
            root_speed = np.linalg.norm(np.diff(roots[:, :3], axis=0)[:, [0, 2]], axis=-1) * contract["fps"]
            phase = manifest["clips"][index]["labels"]["phase"]
            group = (contract["clips"][index]["category"], phase,
                     speed_bin(float(root_speed.mean())))
            self.groups.append(group)
            self.group_counts[group] += 1
        raw = np.array([self.group_counts[group] ** -.5 for group in self.groups], dtype=np.float64)
        self.weights = np.clip(raw / raw.mean(), .5, 3.)

    def __getitem__(self, item):
        if isinstance(item, tuple):
            item, repeat = item
        else:
            repeat = 0
        index, values, roots, original = self.clips[item]
        start = random.Random(self.seed + self.epoch * 1000003 + index + repeat * 7919).randrange(len(values) - 71)
        values = values[start:start + 72]
        source_roots = roots[start:start + 72]
        contacts = self.v2[index] if self.arm == "toe_witness" else original
        contacts = contacts[start + 48:start + 72]
        history0 = np.concatenate((values[:24], root_local(source_roots[:24], source_roots[23])), axis=-1)
        root1 = root_local(source_roots[24:48], source_roots[23])
        history1 = np.concatenate((values[24:48], root_local(source_roots[24:48], source_roots[47])), axis=-1)
        root2 = root_local(source_roots[48:72], source_roots[47])
        arrays = (history0, root1, history1, root2, values[48:72], contacts)
        return tuple(torch.from_numpy(np.ascontiguousarray(part, dtype=np.float32)) for part in arrays)

    def speed_phase_plan(self, epoch):
        """80% unique clips, 20% rarity-weighted draws, each clip at most twice."""
        rng = np.random.default_rng(self.seed + epoch * 1000003 + 71)
        n = len(self.clips)
        base = rng.permutation(n)[:int(.8 * n)].tolist()
        used = Counter(base)
        plan = [(index, 0) for index in base]
        while len(plan) < n:
            weight = np.where(np.array([used[i] < 2 for i in range(n)]), self.weights, 0.)
            weight /= weight.sum()
            choice = int(rng.choice(n, p=weight))
            plan.append((choice, used[choice]))
            used[choice] += 1
        rng.shuffle(plan)
        histogram = Counter("/".join(self.groups[index]) for index, _ in plan)
        return plan, {"epoch": epoch + 1, "draws": n, "unique_clips": len(used),
                      "repeat_draws": n - len(used), "group_draws": dict(sorted(histogram.items()))}


def one_epoch(model, loader, optimizer, mean, std, feet, *, epoch, seed, contact_weight):
    model.train()
    sums = np.zeros(3, dtype=np.float64)
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
        use_generated = torch.rand((len(h0), 1, 1), generator=generator, device="cuda") < .75
        history = torch.where(use_generated, generated, h1_true)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            prediction = model(history, r2, reference, mask).float()
            loss, position, rotation = losses(prediction, target, mask, std,
                                              pose_mean=mean, root_plan=r2, contacts=contacts,
                                              foot_indices=feet, contact_weight=contact_weight)
        if not torch.isfinite(loss):
            raise ValueError(f"Nonfinite loss at epoch {epoch+1} step {step}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
        optimizer.step()
        sums += np.array((loss.item(), position.item(), rotation.item())) * len(h0)
        if step % 30 == 0 or step == len(loader):
            print(f"epoch={epoch+1} step={step}/{len(loader)} elapsed_s={time.monotonic()-started:.1f}", flush=True)
    return {"epoch": epoch + 1, "loss": float(sums[0] / len(loader.dataset)),
            "pose_axis_rmse_cm": float(np.sqrt(sums[1] / len(loader.dataset)) * 100),
            "rotation_6d_mse": float(sums[2] / len(loader.dataset)),
            "seconds": time.monotonic() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initial", type=Path, default=INITIAL)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--seed", type=int, default=20260927)
    parser.add_argument("--max-clips", type=int)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=ARMS)
    parser.add_argument("--contact-weight", type=float, default=.0005)
    args = parser.parse_args()
    if args.output.exists() or min(args.epochs, args.batch_size) < 1:
        parser.error("Output must be new and counts positive")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required")
    contract, lock = verify_release(RELEASE, LOCK)
    initial = torch.load(args.initial, map_location="cpu", weights_only=False)
    if initial["config"]["contract_sha256"] != lock["artifacts_sha256"]["contract/contract.json"]:
        raise ValueError("Checkpoint/frozen contract mismatch")
    stats = contract["stats"]["pose_m"]
    mean_np = np.load(RELEASE / "contract/stats" / stats["mean"]).astype(np.float32)
    std_np = np.load(RELEASE / "contract/stats" / stats["std"]).astype(np.float32)
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in ROLES]
    data = PilotClips(contract, mean_np, std_np, feet, seed=args.seed, max_clips=args.max_clips)
    mean, std = torch.from_numpy(mean_np).to("cuda"), torch.from_numpy(std_np).to("cuda")
    config = {"contract_sha256": initial["config"]["contract_sha256"],
              "source_manifest_sha256": contract["source_manifest_sha256"],
              "initial_checkpoint": str(args.initial.resolve()),
              "initial_checkpoint_sha256": sha256(args.initial),
              "train_clips": len(data), "clip_indices": [row[0] for row in data.clips],
              "epochs": args.epochs, "batch_size": args.batch_size, "lr": args.lr, "seed": args.seed,
              "generated_history_probability": .75, "contact_weight": args.contact_weight,
              "toe_witness_added_bits": dict(data.added_bits),
              "speed_phase_policy": "80% unique baseline pool + 20% inverse-sqrt(category, phase, full-clip speed-bin) draws; max 2 per clip",
              "root_condition": "paired source future Root, no future pose reference",
              "device": torch.cuda.get_device_name(0), "torch": torch.__version__}
    args.output.mkdir(parents=True)
    (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    for arm in args.arms:
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        random.seed(args.seed)
        model = ReferenceGuidedPose(contract["bone_count"], initial["config"]["width"]).to("cuda")
        model.load_state_dict(initial["model"])
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=.01)
        data.arm = arm
        history, plans = [], []
        arm_dir = args.output / arm
        arm_dir.mkdir()
        for epoch in range(args.epochs):
            data.epoch = epoch
            if arm == "speed_phase":
                plan, report = data.speed_phase_plan(epoch)
                plans.append(report)
                loader = DataLoader(data, batch_size=args.batch_size, sampler=plan,
                                    num_workers=0, pin_memory=True)
            else:
                loader = DataLoader(data, batch_size=args.batch_size, shuffle=True,
                                    num_workers=0, pin_memory=True,
                                    generator=torch.Generator().manual_seed(args.seed))
            metrics = one_epoch(model, loader, optimizer, mean, std, feet,
                                epoch=epoch, seed=args.seed, contact_weight=args.contact_weight)
            history.append(metrics)
            checkpoint_config = dict(initial["config"], experiment="2026-09-27-contact-v2-pilot",
                                     arm=arm, fine_tune_config=config, fine_tune_epoch=epoch + 1)
            torch.save({"model": model.state_dict(), "config": checkpoint_config,
                        "epoch": epoch + 1, "metrics": metrics},
                       arm_dir / f"epoch_{epoch+1:03}.pt")
            print(json.dumps({"arm": arm, **metrics}), flush=True)
        (arm_dir / "metrics.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
        if plans:
            (arm_dir / "sampling_plans.json").write_text(json.dumps(plans, indent=2) + "\n", encoding="utf-8")
        del model, optimizer, loader
        torch.cuda.empty_cache()
    print(json.dumps({"output": str(args.output.resolve()), "train_clips": len(data)}), flush=True)


if __name__ == "__main__":
    main()
