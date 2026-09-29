"""Compare MotionWeaver checkpoints on fixed held-out Pose Token targets.

This is a paired-oracle Actor Root diagnostic. It does not measure controller
Root prediction, body reconstruction, foot contact, or UE skinned quality.
"""

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from hydra.utils import instantiate
from omegaconf import OmegaConf, open_dict

from motionbricks.data.motionweaver_dataset import MotionWeaverUnrealDataset, collate_motionweaver
from motionbricks.data.unreal_dataset import file_sha256
from motionbricks.helper.pl_util import load_motion_rep


PROFILE = "actor_root_history4_compact_v1"
ACTIONS = ("walk", "run", "crouch")


def validation_indices(manifest, seed, per_action):
    grouped = defaultdict(list)
    for index, clip in enumerate(manifest["clips"]):
        if clip["split"] == "validation" and clip["labels"]["action"] in ACTIONS:
            grouped[clip["labels"]["action"]].append(index)
    rng = random.Random(seed)
    chosen = []
    for action in ACTIONS:
        candidates = grouped[action]
        if len(candidates) < per_action:
            raise ValueError(f"Validation has only {len(candidates)} {action} clips")
        chosen.extend(sorted(rng.sample(candidates, per_action)))
    return chosen


def load_model(checkpoint_path, dataset, sidecar, vqvae, device):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    contract = checkpoint.get("unreal_contract", {})
    if contract.get("kind") != "pose" or contract.get("signature") != dataset.manifest["training_signature"]:
        raise ValueError(f"Pose checkpoint or training signature mismatch: {checkpoint_path}")
    if contract.get("motionweaver_profile") != PROFILE:
        raise ValueError(f"Checkpoint is not an Actor Root conditioned MotionWeaver model: {checkpoint_path}")
    config = OmegaConf.create(contract["config"])
    if config.motionweaver_actor_root_manifest_sha256 != file_sha256(sidecar / "actor_roots_manifest.json"):
        raise ValueError("Checkpoint Actor Root sidecar hash mismatch")
    if config.model.args.vqvae_sha256 != file_sha256(vqvae):
        raise ValueError("Checkpoint VQ codebook hash mismatch")
    with open_dict(config):
        config.data.folder = str(dataset.folder)
        config.skeleton.folder = str(dataset.folder)
        config.motion_rep.stats.folder = str(dataset.folder / "stats")
        config.model.args.vqvae_model_ckpt_path = str(vqvae)
    motion_rep = load_motion_rep(config)
    model_config = config.model
    pose_net = instantiate(model_config.pose_vqvae_network, motion_rep=motion_rep.dual_rep.local_motion_rep)
    backbone = instantiate(model_config.backbone_network, motion_rep=motion_rep, _recursive_=False)
    model = instantiate(model_config, pose_vqvae_network=pose_net, root_vqvae_network=None,
                        backbone_network=backbone, motion_rep=motion_rep,
                        optimizer=instantiate(model_config.optimizer), scheduler=instantiate(model_config.scheduler),
                        _recursive_=False)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    return model.eval().to(device), checkpoint, config


def evaluate(model, dataset, indices, seed, device):
    totals = defaultdict(lambda: {"weighted_loss": 0.0, "target_tokens": 0, "clips": 0})
    for index in indices:
        np.random.seed(seed + index)
        torch.manual_seed(seed + index)
        batch = collate_motionweaver([dataset[index]])
        batch = {key: value.to(device) if isinstance(value, torch.Tensor) else value
                 for key, value in batch.items()}
        metrics = {}
        with torch.inference_mode():
            model.training_step(batch, 0, use_outside_training=True, meta_info=metrics)
        count = int(batch["focused_token_mask"].sum())
        loss = float(metrics["losses"]["pose_loss"])
        if count < 1 or not np.isfinite(loss):
            raise ValueError(f"Invalid validation token loss at clip {index}")
        action = dataset.manifest["clips"][index]["labels"]["action"]
        for name in (action, "overall"):
            totals[name]["weighted_loss"] += loss * count
            totals[name]["target_tokens"] += count
            totals[name]["clips"] += 1
    return {action: {"pose_token_ce_nats": row["weighted_loss"] / row["target_tokens"],
                     "target_tokens": row["target_tokens"], "clips": row["clips"]}
            for action, row in totals.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True, nargs="+")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--actor_root_sidecar", type=Path, required=True)
    parser.add_argument("--vqvae", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--per_action", type=int, default=16)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dataset = MotionWeaverUnrealDataset(args.dataset, args.actor_root_sidecar)
    indices = validation_indices(dataset.manifest, args.seed, args.per_action)
    reports = []
    for checkpoint_path in args.checkpoint:
        model, checkpoint, config = load_model(checkpoint_path.resolve(), dataset,
                                               args.actor_root_sidecar.resolve(), args.vqvae.resolve(), args.device)
        scores = evaluate(model, dataset, indices, args.seed, args.device)
        reports.append({"checkpoint": str(checkpoint_path.resolve()), "checkpoint_sha256": file_sha256(checkpoint_path),
                        "global_step": checkpoint.get("global_step"),
                        "scheduler_total_steps": config.model.scheduler.num_training_steps,
                        "scores": scores})
        del model, checkpoint
        if args.device == "cuda":
            torch.cuda.empty_cache()
    report = {"metric": "masked_pose_token_cross_entropy_nats", "condition": "paired_source_actor_root_teacher",
              "split": "validation", "seed": args.seed, "per_action": args.per_action,
              "indices": indices, "manifest_sha256": file_sha256(args.dataset / "dataset.json"),
              "sidecar_manifest_sha256": file_sha256(args.actor_root_sidecar / "actor_roots_manifest.json"),
              "reports": reports}
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
