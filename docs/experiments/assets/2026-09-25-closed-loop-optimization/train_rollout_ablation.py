"""Matched fine-tuning of real-history, generated-history, and contact arms.

This is an experimental no-reference training script. It never changes the
frozen contract or source clips and writes new checkpoints only.
"""

import argparse
import base64
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from data.runtime.conditioned_motion import load_raw, root_local
from training.pretrain.train_conditioned_pose import ReferenceGuidedPose, losses, verify_release


ROOT = Path(__file__).resolve().parents[4]
RELEASE = Path(r"E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924")
LOCK = ROOT / "data/freezes/reference_guided_root_pose_v1_20260924.json"
INITIAL = Path(r"E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_uniform12\epoch_012.pt")
CATEGORIES = ("Walk", "Run", "Crouch")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def orthogonal_first_two(values):
    """Match inference.runtime.conditioned_pose.rotation_6d_to_matrix."""
    first = values[..., [0, 2, 4]]
    second = values[..., [1, 3, 5]]
    first_norm = torch.linalg.vector_norm(first, dim=-1, keepdim=True)
    first = torch.where(first_norm > 1e-6, first / first_norm.clamp_min(1e-6),
                        torch.tensor([1., 0., 0.], device=values.device))
    second = second - torch.sum(first * second, dim=-1, keepdim=True) * first
    second_norm = torch.linalg.vector_norm(second, dim=-1, keepdim=True)
    fallback = torch.where(torch.abs(first[..., :1]) < 0.9,
                           torch.tensor([1., 0., 0.], device=values.device),
                           torch.tensor([0., 1., 0.], device=values.device))
    fallback = F.normalize(fallback - (fallback * first).sum(-1, keepdim=True) * first, dim=-1)
    second = torch.where(second_norm > 1e-6, second / second_norm.clamp_min(1e-6), fallback)
    return torch.stack((first, second), dim=-1).reshape(*values.shape[:-1], 6)


class ThreeWindowClips(Dataset):
    def __init__(self, contract, mean, std, *, seed, max_clips=None):
        self.contract = contract
        self.mean = mean
        self.std = std
        self.seed = seed
        self.epoch = 0
        selected = [(index, clip) for index, clip in enumerate(contract["clips"])
                    if clip["split"] == "train" and clip["category"] in CATEGORIES
                    and clip["source_frames"] >= 72]
        if max_clips is not None:
            selected = selected[:max_clips]
        self.clips = []
        source = Path(contract["source_dataset"])
        for number, (index, clip) in enumerate(selected, 1):
            raw, _ = load_raw(source / clip["raw_file"], clip["source_frames"],
                              contract["bone_count"], contract["fps"],
                              expected_sha256=clip["raw_sha256"])
            packed = np.frombuffer(base64.b64decode(clip["contact_bits"]), dtype=np.uint8)
            contacts = np.unpackbits(packed)[:clip["source_frames"] * 4].reshape(-1, 4).astype(np.float32)
            pose = ((raw["positions"] - mean) / std).astype(np.float32)
            rotations = raw["rotations"][..., :2].reshape(clip["source_frames"],
                                                            contract["bone_count"], 6).astype(np.float32)
            combined = np.concatenate((pose, rotations), axis=-1).reshape(clip["source_frames"], -1)
            self.clips.append((index, combined, raw["root_track"], contacts))
            if number % 200 == 0 or number == len(selected):
                print(f"loaded and hash-checked {number}/{len(selected)} train clips", flush=True)

    def __len__(self):
        return len(self.clips)

    def __getitem__(self, item):
        index, values, roots, contacts = self.clips[item]
        start = random.Random(self.seed + self.epoch * 1000003 + index).randrange(len(values) - 71)
        values = values[start:start + 72]
        roots = roots[start:start + 72]
        contacts = contacts[start + 48:start + 72]
        history0 = np.concatenate((values[:24], root_local(roots[:24], roots[23])), axis=-1)
        root1 = root_local(roots[24:48], roots[23])
        history1_root = root_local(roots[24:48], roots[47])
        history1_true = np.concatenate((values[24:48], history1_root), axis=-1)
        root2 = root_local(roots[48:72], roots[47])
        arrays = (history0, root1, history1_true, root2, values[48:72], contacts)
        return tuple(torch.from_numpy(np.ascontiguousarray(value)) for value in arrays)


def one_epoch(model, loader, optimizer, mean, std, feet, *, arm, contact_weight,
              seed, epoch, log_every):
    model.train()
    sums = np.zeros(3, dtype=np.float64)
    generated_count = 0
    start_time = time.monotonic()
    generator = torch.Generator(device="cuda").manual_seed(seed + epoch * 1000003)
    for step, batch in enumerate(loader, 1):
        h0, r1, h1_true, r2, target, contacts = [part.to("cuda", non_blocking=True) for part in batch]
        reference = torch.zeros((len(h0), 24, model.features), device="cuda")
        mask = torch.zeros((len(h0), 24, 1), device="cuda")
        history = h1_true
        if arm != "real_history":
            model.eval()
            with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                first = model(h0, r1, reference, mask).float().reshape(len(h0), 24, model.bones, 9)
            model.train()
            first = torch.cat((first[..., :3], orthogonal_first_two(first[..., 3:])), dim=-1)
            generated = torch.cat((first.reshape(len(h0), 24, -1), h1_true[..., -7:]), dim=-1)
            use_generated = torch.rand((len(h0), 1, 1), generator=generator, device="cuda") < 0.75
            history = torch.where(use_generated, generated, h1_true)
            generated_count += int(use_generated.sum().item())
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            prediction = model(history, r2, reference, mask)
            loss, position, rotation = losses(prediction.float(), target, mask, std,
                                              pose_mean=mean, root_plan=r2, contacts=contacts,
                                              foot_indices=feet, contact_weight=contact_weight)
        if not torch.isfinite(loss):
            raise ValueError(f"nonfinite loss: {arm} epoch={epoch + 1} step={step}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        sums += np.array((loss.item(), position.item(), rotation.item())) * len(h0)
        if step % log_every == 0 or step == len(loader):
            print(f"{arm} epoch={epoch + 1} step={step}/{len(loader)} "
                  f"loss={sums[0] / (step * loader.batch_size):.5f} "
                  f"elapsed_s={time.monotonic() - start_time:.0f}", flush=True)
    return {"loss": sums[0] / len(loader.dataset),
            "pose_axis_rmse_cm": float(np.sqrt(sums[1] / len(loader.dataset)) * 100),
            "rotation_6d_mse": sums[2] / len(loader.dataset),
            "generated_history_samples": generated_count,
            "seconds": time.monotonic() - start_time}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--max-clips", type=int)
    parser.add_argument("--arms", nargs="+", choices=("real_history", "generated_history", "generated_contact"),
                        default=("real_history", "generated_history", "generated_contact"))
    parser.add_argument("--contact-weight", type=float, default=0.0005)
    parser.add_argument("--log-every", type=int, default=30)
    args = parser.parse_args()
    if args.output.exists() or min(args.epochs, args.batch_size, args.log_every) <= 0:
        parser.error("output must not exist and training counts must be positive")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the matched fine-tuning")
    contract, lock = verify_release(RELEASE, LOCK)
    original = torch.load(INITIAL, map_location="cpu", weights_only=False)
    if original["config"]["contract_sha256"] != lock["artifacts_sha256"]["contract/contract.json"]:
        raise ValueError("Initial checkpoint and frozen contract mismatch")
    stats = contract["stats"]["pose_m"]
    mean_np = np.load(RELEASE / "contract/stats" / stats["mean"]).astype(np.float32)
    std_np = np.load(RELEASE / "contract/stats" / stats["std"]).astype(np.float32)
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in
            ("left_foot", "left_toe", "right_foot", "right_toe")]
    dataset = ThreeWindowClips(contract, mean_np, std_np, seed=args.seed, max_clips=args.max_clips)
    mean = torch.from_numpy(mean_np).to("cuda")
    std = torch.from_numpy(std_np).to("cuda")
    args.output.mkdir(parents=True)
    base_config = {"contract_sha256": original["config"]["contract_sha256"],
                   "initial_checkpoint": str(INITIAL), "initial_checkpoint_sha256": sha256(INITIAL),
                   "source_manifest_sha256": contract["source_manifest_sha256"],
                   "train_clips": len(dataset), "clip_indices": [row[0] for row in dataset.clips],
                   "categories": CATEGORIES, "epochs": args.epochs, "batch_size": args.batch_size,
                   "lr": args.lr, "seed": args.seed, "generated_history_probability": 0.75,
                   "contact_weight_for_generated_contact": args.contact_weight,
                   "history_windows": 24, "target_window": 24,
                   "training_root": "source future Root; no future pose reference",
                   "device": torch.cuda.get_device_name(0), "torch": torch.__version__}
    (args.output / "config.json").write_text(json.dumps(base_config, indent=2) + "\n", encoding="utf-8")
    for arm in args.arms:
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        random.seed(args.seed)
        model = ReferenceGuidedPose(contract["bone_count"], original["config"]["width"]).to("cuda")
        model.load_state_dict(original["model"])
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
        loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=0,
                            pin_memory=True, generator=torch.Generator().manual_seed(args.seed))
        arm_dir = args.output / arm
        arm_dir.mkdir()
        history = []
        weight = args.contact_weight if arm == "generated_contact" else 0.0
        for epoch in range(args.epochs):
            dataset.epoch = epoch
            metrics = one_epoch(model, loader, optimizer, mean, std, feet, arm=arm,
                                contact_weight=weight, seed=args.seed, epoch=epoch,
                                log_every=args.log_every)
            metrics["epoch"] = epoch + 1
            history.append(metrics)
            config = dict(original["config"], experiment="generated_history_contact_ablation",
                          arm=arm, fine_tune_config=base_config, contact_weight=weight,
                          initial_checkpoint=str(INITIAL), fine_tune_epoch=epoch + 1)
            torch.save({"model": model.state_dict(), "config": config, "epoch": epoch + 1,
                        "metrics": metrics}, arm_dir / f"epoch_{epoch + 1:03}.pt")
            print(json.dumps({"arm": arm, **metrics}), flush=True)
        (arm_dir / "metrics.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
        del model, optimizer, loader
        torch.cuda.empty_cache()
    print(json.dumps({"output": str(args.output.resolve()), "train_clips": len(dataset)}), flush=True)


if __name__ == "__main__":
    main()
