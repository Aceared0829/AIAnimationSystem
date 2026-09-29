"""Depth-2 generated-history recovery experiment for the third 24-frame block."""

import argparse
import importlib.util
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from data.runtime.conditioned_motion import root_local
from training.pretrain.train_conditioned_pose import ReferenceGuidedPose, losses, verify_release


ROOT = Path(__file__).resolve().parents[4]
PARENT_SCRIPT = Path(__file__).with_name("train_rollout_ablation.py")


def load_parent():
    spec = importlib.util.spec_from_file_location("single_step_training", PARENT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FourWindowClips:
    def __init__(self, parent, contract, mean, std, seed):
        self.parent = parent
        self.base = parent.ThreeWindowClips(contract, mean, std, seed=seed)
        self.clips = [clip for clip in self.base.clips if len(clip[1]) >= 96]
        self.seed = seed
        self.epoch = 0

    def __len__(self):
        return len(self.clips)

    def __getitem__(self, item):
        index, values, roots, contacts = self.clips[item]
        start = random.Random(self.seed + self.epoch * 1000003 + index).randrange(len(values) - 95)
        values, roots = values[start:start + 96], roots[start:start + 96]
        contacts = contacts[start + 72:start + 96]
        h0 = np.concatenate((values[:24], root_local(roots[:24], roots[23])), axis=-1)
        r1 = root_local(roots[24:48], roots[23])
        h1 = np.concatenate((values[24:48], root_local(roots[24:48], roots[47])), axis=-1)
        r2 = root_local(roots[48:72], roots[47])
        h2 = np.concatenate((values[48:72], root_local(roots[48:72], roots[71])), axis=-1)
        r3 = root_local(roots[72:96], roots[71])
        return tuple(torch.from_numpy(np.ascontiguousarray(value)) for value in
                     (h0, r1, h1, r2, h2, r3, values[72:96], contacts))


def generated_history(parent, model, history, future_root, next_true_history, reference, mask):
    with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
        predicted = model(history, future_root, reference, mask).float().reshape(
            len(history), 24, model.bones, 9)
    fixed = torch.cat((predicted[..., :3], parent.orthogonal_first_two(predicted[..., 3:])), dim=-1)
    return torch.cat((fixed.reshape(len(history), 24, -1), next_true_history[..., -7:]), dim=-1)


def train_epoch(parent, model, loader, optimizer, mean, std, feet, *, arm, contact_weight, seed, epoch):
    model.train()
    total = 0.0
    generated_samples = 0
    rng = torch.Generator(device="cuda").manual_seed(seed + epoch * 1000003)
    started = time.monotonic()
    for batch in loader:
        h0, r1, h1, r2, h2, r3, target, contacts = [part.to("cuda", non_blocking=True) for part in batch]
        reference = torch.zeros((len(h0), 24, model.features), device="cuda")
        mask = torch.zeros((len(h0), 24, 1), device="cuda")
        history = h2
        if arm != "real_history":
            model.eval()
            first = generated_history(parent, model, h0, r1, h1, reference, mask)
            second = generated_history(parent, model, first, r2, h2, reference, mask)
            model.train()
            choose = torch.rand((len(h0), 1, 1), generator=rng, device="cuda") < 0.75
            history = torch.where(choose, second, h2)
            generated_samples += int(choose.sum())
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            prediction = model(history, r3, reference, mask)
            loss, _, _ = losses(prediction.float(), target, mask, std, pose_mean=mean,
                                root_plan=r3, contacts=contacts, foot_indices=feet,
                                contact_weight=contact_weight)
        if not torch.isfinite(loss):
            raise ValueError("nonfinite loss")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total += float(loss) * len(h0)
    return {"epoch": epoch + 1, "train_loss": total / len(loader.dataset),
            "generated_history_samples": generated_samples,
            "seconds": time.monotonic() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--contact-weight", type=float, default=0.0005)
    args = parser.parse_args()
    if args.output.exists() or not torch.cuda.is_available():
        raise RuntimeError("new output directory and CUDA required")
    parent = load_parent()
    contract, lock = verify_release(parent.RELEASE, parent.LOCK)
    initial = torch.load(parent.INITIAL, map_location="cpu", weights_only=False)
    if initial["config"]["contract_sha256"] != lock["artifacts_sha256"]["contract/contract.json"]:
        raise ValueError("contract mismatch")
    stats = contract["stats"]["pose_m"]
    mean_np = np.load(parent.RELEASE / "contract/stats" / stats["mean"]).astype(np.float32)
    std_np = np.load(parent.RELEASE / "contract/stats" / stats["std"]).astype(np.float32)
    dataset = FourWindowClips(parent, contract, mean_np, std_np, args.seed)
    mean, std = torch.from_numpy(mean_np).to("cuda"), torch.from_numpy(std_np).to("cuda")
    skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
    names = [bone["name"] for bone in skeleton["bones"]]
    feet = [names.index(skeleton["roles"][role]) for role in
            ("left_foot", "left_toe", "right_foot", "right_toe")]
    args.output.mkdir(parents=True)
    config = {"initial_checkpoint": str(parent.INITIAL), "initial_sha256": parent.sha256(parent.INITIAL),
              "contract_sha256": initial["config"]["contract_sha256"], "train_clips": len(dataset),
              "clip_indices": [row[0] for row in dataset.clips], "epochs": args.epochs,
              "batch_size": args.batch_size, "lr": args.lr, "seed": args.seed,
              "generated_history_probability": 0.75, "contact_weight": args.contact_weight,
              "source_future_root": True, "reference": "none", "unroll_depth": 2,
              "device": torch.cuda.get_device_name(0)}
    (args.output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    for arm in ("real_history", "generated_history", "generated_contact"):
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
        history = []
        contact_weight = args.contact_weight if arm == "generated_contact" else 0.0
        for epoch in range(args.epochs):
            dataset.epoch = epoch
            metrics = train_epoch(parent, model, loader, optimizer, mean, std, feet, arm=arm,
                                  contact_weight=contact_weight, seed=args.seed, epoch=epoch)
            history.append(metrics)
            model_config = dict(initial["config"], experiment="two_step_generated_history",
                                arm=arm, unroll_depth=2, fine_tune_config=config,
                                contact_weight=contact_weight)
            torch.save({"model": model.state_dict(), "config": model_config,
                        "epoch": epoch + 1, "metrics": metrics}, folder / f"epoch_{epoch + 1:03}.pt")
            print(json.dumps({"arm": arm, **metrics}), flush=True)
        (folder / "metrics.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
        del model, optimizer, loader
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
