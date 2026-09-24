"""从封版 Root/硬参考契约训练未来 Root 相对姿态的首轮条件生成器。"""

import argparse
import base64
import hashlib
import json
import math
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

from data.runtime.conditioned_motion import load_raw, root_local
from motionbricks.data.unreal_dataset import contained_file


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_release(release, lock, source_override=None):
    release = Path(release).resolve()
    lock = json.loads(Path(lock).read_text(encoding="utf-8"))
    if json.loads((release / "freeze_manifest.json").read_text(encoding="utf-8")) != lock:
        raise ValueError("封版清单与仓库锁不一致")
    for name, expected in lock["artifacts_sha256"].items():
        if digest(release / name) != expected:
            raise ValueError(f"封版文件哈希不匹配：{name}")
    contract = json.loads((release / "contract" / "contract.json").read_text(encoding="utf-8"))
    source = Path(source_override if source_override is not None else contract["source_dataset"]).resolve()
    if digest(source / "dataset.json") != contract["source_manifest_sha256"]:
        raise ValueError("来源清单已改变")
    if digest(source / "skeleton.json") != contract["skeleton_sha256"]:
        raise ValueError("来源骨架已改变")
    if contract["window"]["history_frames"] != 24 or contract["window"]["future_frames"] != 24:
        raise ValueError("当前模型要求 24+24 帧契约")
    # 位置可迁移，内容仍由冻结清单、骨架与逐条 NPZ 哈希约束。
    return dict(contract, source_dataset=str(source)), lock


class MotionWindows(Dataset):
    def __init__(self, release, contract, split, *, seed=42, scenario="random", include_contacts=False):
        self.contract = contract
        self.split = split
        self.seed = seed
        self.scenario = scenario
        self.include_contacts = include_contacts
        self.epoch = 0
        self.rows = []
        with (Path(release) / "contract" / "windows.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if contract["clips"][row["clip_index"]]["split"] == split:
                    self.rows.append(row)
        if len(self.rows) != contract["window_split_counts"][split]:
            raise ValueError(f"{split} 窗口数与封版不一致")
        source = Path(contract["source_dataset"])
        self.raw = {}
        self.contacts = {}
        indices = sorted({row["clip_index"] for row in self.rows})
        for count, index in enumerate(indices, 1):
            clip = contract["clips"][index]
            raw, _ = load_raw(contained_file(source, clip["raw_file"]), clip["source_frames"],
                              contract["bone_count"], contract["fps"], expected_sha256=clip["raw_sha256"])
            self.raw[index] = (raw["positions"], raw["rotations"][..., :2].reshape(
                clip["source_frames"], contract["bone_count"], 6).copy(), raw["root_track"])
            if include_contacts:
                packed = np.frombuffer(base64.b64decode(clip["contact_bits"]), dtype=np.uint8)
                self.contacts[index] = np.unpackbits(packed)[:clip["source_frames"] * 4].reshape(
                    clip["source_frames"], 4).astype(np.float32)
            if count % 200 == 0 or count == len(indices):
                print(f"{split} 哈希校验并缓存 {count}/{len(indices)} 条动作", flush=True)
        stats = contract["stats"]["pose_m"]
        self.mean = np.load(Path(release) / "contract" / "stats" / stats["mean"]).astype(np.float32)
        self.std = np.load(Path(release) / "contract" / "stats" / stats["std"]).astype(np.float32)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, item):
        row = self.rows[item]
        positions, rotations, root = self.raw[row["clip_index"]]
        start = row["start"]
        middle, end = start + 24, start + 48
        origin = root[middle - 1]
        pose = (positions[start:end] - self.mean) / self.std
        combined = np.concatenate((pose, rotations[start:end]), axis=-1).reshape(48, -1).astype(np.float32)
        history_root = root_local(root[start:middle], origin)
        future_root = root_local(root[middle:end], origin)
        history = np.concatenate((combined[:24], history_root), axis=-1)
        target = combined[24:]
        if self.scenario in ("random", "diverse", "hybrid"):
            rng = np.random.default_rng(self.seed + self.epoch * 1000003 + item)
            legacy = self.scenario == "random" or (self.scenario == "hybrid" and rng.random() < 0.5)
            if legacy:
                offsets = ((), (12,), (23,), (12, 23))[int(rng.integers(4))]
            else:
                count = int(rng.choice(4, p=(0.25, 0.35, 0.35, 0.05)))
                offsets = tuple(sorted(rng.choice(24, count, replace=False).tolist()))
        elif self.scenario == "one_ref":
            offsets = (12,)
        elif self.scenario == "two_refs":
            offsets = (12, 23)
        else:
            offsets = ()
        mask = np.zeros((24, 1), dtype=np.float32)
        mask[list(offsets)] = 1
        reference = target * mask
        result = (torch.from_numpy(history), torch.from_numpy(future_root),
                  torch.from_numpy(reference), torch.from_numpy(mask), torch.from_numpy(target))
        if self.include_contacts:
            result += (torch.from_numpy(self.contacts[row["clip_index"]][middle:end]),)
        return result


def balanced_window_weights(data, category_power=0.5, clip_power=0.5):
    """Weight existing windows without moving clips across the frozen split."""
    if not 0 <= category_power <= 1 or not 0 <= clip_power <= 1:
        raise ValueError("sampling powers must be in [0, 1]")
    categories = Counter(data.contract["clips"][row["clip_index"]]["category"] for row in data.rows)
    clips = Counter(row["clip_index"] for row in data.rows)
    weights = [categories[data.contract["clips"][row["clip_index"]]["category"]] ** -category_power
               * clips[row["clip_index"]] ** -clip_power for row in data.rows]
    return torch.tensor(weights, dtype=torch.double)


def capture_random_state(loader_generator):
    return {"python": random.getstate(), "numpy": np.random.get_state(),
            "torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all(),
            "loader": loader_generator.get_state()}


def restore_random_state(state, loader_generator):
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"].cpu())
    torch.cuda.set_rng_state_all([value.cpu() for value in state["cuda"]])
    loader_generator.set_state(state["loader"].cpu())


def root_world_positions(local_pose, root_plan):
    """Apply the Root quaternion (xyzw) to local positions in torch."""
    quaternion = root_plan[..., 3:]
    vector = quaternion[..., :3].unsqueeze(-2)
    translation = root_plan[..., :3].unsqueeze(-2)
    twice_cross = 2 * torch.cross(vector.expand_as(local_pose), local_pose, dim=-1)
    return (local_pose + quaternion[..., 3:4].unsqueeze(-2) * twice_cross
            + torch.cross(vector.expand_as(local_pose), twice_cross, dim=-1) + translation)


class ReferenceGuidedPose(nn.Module):
    def __init__(self, bones=79, width=256):
        super().__init__()
        self.bones = bones
        self.features = bones * 9
        self.history = nn.GRU(self.features + 7, width, batch_first=True)
        self.control = nn.Linear(self.features + 8, width)
        self.time = nn.Parameter(torch.zeros(1, 24, width))
        layer = nn.TransformerEncoderLayer(width, 4, width * 3, dropout=0.1, batch_first=True,
                                           norm_first=True)
        self.temporal = nn.TransformerEncoder(layer, 3)
        self.output = nn.Sequential(nn.LayerNorm(width), nn.Linear(width, self.features))

    def forward(self, history, root_plan, reference, mask):
        _, state = self.history(history)
        control = torch.cat((root_plan, reference, mask), dim=-1)
        hidden = self.control(control) + state[-1].unsqueeze(1) + self.time
        predicted = self.output(self.temporal(hidden))
        return torch.where(mask.bool(), reference, predicted)


def losses(predicted, target, mask, pose_std, *, pose_mean=None, root_plan=None, contacts=None,
           foot_indices=None, contact_weight=0.0):
    batch, frames = target.shape[:2]
    predicted = predicted.reshape(batch, frames, -1, 9)
    target = target.reshape(batch, frames, -1, 9)
    visible = (1 - mask).reshape(batch, frames, 1, 1)
    count = visible.sum() * predicted.shape[2]
    position = (((predicted[..., :3] - target[..., :3]) * pose_std) ** 2 * visible).sum() / (count * 3)
    rotation = (((predicted[..., 3:] - target[..., 3:]) ** 2) * visible).sum() / (count * 6)
    velocity = (((predicted[:, 1:, :, :3] - predicted[:, :-1, :, :3]
                  - target[:, 1:, :, :3] + target[:, :-1, :, :3]) * pose_std) ** 2).mean()
    total = 10 * position + rotation + 2 * velocity
    if contact_weight:
        if pose_mean is None or root_plan is None or contacts is None or foot_indices is None:
            raise ValueError("contact loss requires pose mean, Root, contact labels, and foot indices")
        pose_m = predicted[..., :3] * pose_std + pose_mean
        world_feet = root_world_positions(pose_m[:, :, foot_indices], root_plan)
        speed = torch.linalg.vector_norm(world_feet[:, 1:] - world_feet[:, :-1], dim=-1) * 30
        contact_pairs = contacts[:, 1:] * contacts[:, :-1]
        contact_loss = (speed.square() * contact_pairs).sum() / contact_pairs.sum().clamp_min(1)
        total = total + contact_weight * contact_loss
    return total, position, rotation


@torch.no_grad()
def validate(model, loader, device, pose_std, *, pose_mean=None, foot_indices=None, contact_weight=0.0):
    model.eval()
    totals = np.zeros(3, dtype=np.float64)
    for batch in loader:
        parts = [part.to(device, non_blocking=True) for part in batch]
        history, root, reference, mask, target = parts[:5]
        contacts = parts[5] if len(parts) > 5 else None
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
            predicted = model(history, root, reference, mask)
            loss, pos, rot = losses(predicted.float(), target, mask, pose_std, pose_mean=pose_mean,
                                    root_plan=root,
                                    contacts=contacts, foot_indices=foot_indices,
                                    contact_weight=contact_weight)
        totals += np.array([loss.item(), pos.item(), rot.item()]) * len(history)
    return (totals / len(loader.dataset)).tolist()


def train(args):
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    contract, lock = verify_release(args.release, args.lock, args.source_override)
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(f"训练输出已存在：{output}")
    if not torch.cuda.is_available():
        raise RuntimeError("本轮要求可用 CUDA GPU")
    device = torch.device("cuda")
    print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)
    use_contacts = args.contact_weight > 0
    train_data = MotionWindows(args.release, contract, "train", seed=args.seed,
                               scenario=args.reference_sampling, include_contacts=use_contacts)
    valid_data = MotionWindows(args.release, contract, "validation", seed=args.seed,
                               scenario="two_refs", include_contacts=use_contacts)
    foot_indices = None
    if use_contacts:
        skeleton = json.loads((Path(contract["source_dataset"]) / "skeleton.json").read_text(encoding="utf-8"))
        names = [bone["name"] for bone in skeleton["bones"]]
        foot_indices = [names.index(skeleton["roles"][role]) for role in
                        ("left_foot", "left_toe", "right_foot", "right_toe")]
    generator = torch.Generator().manual_seed(args.seed)
    sampler = (WeightedRandomSampler(balanced_window_weights(train_data, args.category_power,
                                                               args.clip_power), len(train_data),
                                     replacement=True, generator=generator)
               if args.sampling == "balanced" else None)
    train_loader = DataLoader(train_data, batch_size=args.batch_size, shuffle=sampler is None, sampler=sampler,
                              generator=generator,
                              num_workers=0, pin_memory=True)
    valid_loader = DataLoader(valid_data, batch_size=args.batch_size, shuffle=False,
                              num_workers=0, pin_memory=True)
    model = ReferenceGuidedPose(contract["bone_count"], args.width).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    pose_std = torch.from_numpy(train_data.std).to(device)
    pose_mean = torch.from_numpy(train_data.mean).to(device)
    start_epoch = 0
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=device, weights_only=False)
        previous = checkpoint["config"]
        if (previous["contract_sha256"] != lock["artifacts_sha256"]["contract/contract.json"]
                or previous["width"] != args.width or previous["batch_size"] != args.batch_size):
            raise ValueError("续训检查点与封版契约或模型配置不匹配")
        for key, expected in (("sampling", args.sampling), ("reference_sampling", args.reference_sampling),
                              ("category_power", args.category_power), ("clip_power", args.clip_power),
                              ("learning_rate", args.lr), ("contact_weight", args.contact_weight)):
            if previous.get(key, "uniform" if key == "sampling" else "random" if key == "reference_sampling"
                            else 0.5 if key in ("category_power", "clip_power")
                            else 0.0 if key == "contact_weight" else None) != expected:
                raise ValueError(f"续训配置不一致：{key}")
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        start_epoch = checkpoint["epoch"]
        if "random_state" in checkpoint:
            restore_random_state(checkpoint["random_state"], generator)
        else:
            print("警告：旧检查点缺少随机状态，续训无法逐步复现未中断训练", flush=True)
        if args.epochs <= start_epoch:
            raise ValueError("目标训练轮数必须大于续训检查点轮数")
    output.mkdir(parents=True, exist_ok=False)
    config = {"release_id": lock["release_id"], "contract_sha256": lock["artifacts_sha256"]["contract/contract.json"],
              "seed": args.seed, "batch_size": args.batch_size, "width": args.width, "epochs": args.epochs,
              "learning_rate": args.lr, "train_windows": len(train_data), "validation_windows": len(valid_data),
              "source_dataset_runtime": contract["source_dataset"],
              "model": "GRU history + temporal Transformer; Root path and sparse full-pose references",
              "rotation_representation": "first_two_matrix_columns_6d", "control_mode": "oracle_future_root_plan",
              "validation_references": [12, 23],
              "sampling": args.sampling, "reference_sampling": args.reference_sampling,
              "category_power": args.category_power, "clip_power": args.clip_power,
              "contact_weight": args.contact_weight,
              "logged_pose_metric": "coordinate_axis_rmse_cm_not_joint_distance_rmse",
              "resumed_from": str(Path(args.resume).resolve()) if args.resume else None}
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    started = time.monotonic()
    for epoch in range(start_epoch, args.epochs):
        train_data.epoch = epoch
        model.train()
        totals = np.zeros(3, dtype=np.float64)
        for step, batch in enumerate(train_loader, 1):
            parts = [part.to(device, non_blocking=True) for part in batch]
            history, root, reference, mask, target = parts[:5]
            contacts = parts[5] if len(parts) > 5 else None
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                predicted = model(history, root, reference, mask)
                loss, pos, rot = losses(predicted.float(), target, mask, pose_std, pose_mean=pose_mean,
                                        root_plan=root,
                                        contacts=contacts, foot_indices=foot_indices,
                                        contact_weight=args.contact_weight)
            if not torch.isfinite(loss):
                raise ValueError(f"非有限损失：epoch={epoch + 1} step={step}")
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            totals += np.array([loss.item(), pos.item(), rot.item()]) * len(history)
            if step % args.log_every == 0 or step == len(train_loader):
                elapsed = time.monotonic() - started
                print(f"epoch {epoch + 1}/{args.epochs} step {step}/{len(train_loader)} "
                      f"loss={totals[0] / (step * args.batch_size):.5f} "
                      f"pose_axis_rmse_cm={math.sqrt(totals[1] / (step * args.batch_size)) * 100:.2f} "
                      f"elapsed_s={elapsed:.0f}", flush=True)
        valid = validate(model, valid_loader, device, pose_std, pose_mean=pose_mean,
                         foot_indices=foot_indices,
                         contact_weight=args.contact_weight)
        valid_data.scenario = "no_refs"
        valid_no_ref = validate(model, valid_loader, device, pose_std, pose_mean=pose_mean,
                                foot_indices=foot_indices,
                                contact_weight=args.contact_weight)
        valid_data.scenario = "one_ref"
        valid_one_ref = validate(model, valid_loader, device, pose_std, pose_mean=pose_mean,
                                 foot_indices=foot_indices,
                                 contact_weight=args.contact_weight)
        valid_data.scenario = "two_refs"
        metrics = {"epoch": epoch + 1, "train_loss": totals[0] / len(train_data),
                   "train_pose_axis_rmse_cm": math.sqrt(totals[1] / len(train_data)) * 100,
                   "validation_loss": valid[0], "validation_pose_axis_rmse_cm": math.sqrt(valid[1]) * 100,
                   "validation_rotation_6d_mse": valid[2], "elapsed_seconds": time.monotonic() - started}
        metrics["validation_no_reference_pose_axis_rmse_cm"] = math.sqrt(valid_no_ref[1]) * 100
        metrics["validation_one_reference_pose_axis_rmse_cm"] = math.sqrt(valid_one_ref[1]) * 100
        with (output / "metrics.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(metrics) + "\n")
        torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                    "random_state": capture_random_state(generator),
                    "epoch": epoch + 1, "config": config, "metrics": metrics}, output / f"epoch_{epoch + 1:03}.pt")
        print("validation " + json.dumps(metrics), flush=True)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--lock", required=True)
    parser.add_argument("--source-override", help="跨系统迁移后的来源数据目录；逐文件哈希仍按封版契约校验")
    parser.add_argument("--output", required=True)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sampling", choices=("uniform", "balanced"), default="uniform")
    parser.add_argument("--category-power", type=float, default=0.5)
    parser.add_argument("--clip-power", type=float, default=0.5)
    parser.add_argument("--reference-sampling", choices=("random", "diverse", "hybrid"), default="random")
    parser.add_argument("--contact-weight", type=float, default=0.0)
    parser.add_argument("--resume", help="相同封版契约与模型配置的上次检查点")
    parser.add_argument("--log-every", type=int, default=100)
    args = parser.parse_args()
    if min(args.epochs, args.batch_size, args.width, args.log_every) < 1 or args.contact_weight < 0:
        parser.error("训练参数必须为正数")
    train(args)


if __name__ == "__main__":
    main()
