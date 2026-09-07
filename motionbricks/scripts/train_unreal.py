"""使用 Unreal 动画训练 VQ-VAE、Pose 或 Root；不加载 G1 预训练权重。"""

import argparse
import hashlib
from pathlib import Path

import pytorch_lightning as pl
import torch
from hydra.utils import instantiate
from omegaconf import OmegaConf, open_dict
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.loggers import CSVLogger
from torch.utils.data import DataLoader

from motionbricks.data.synthetic_dataset import collate_batch
from motionbricks.data.unreal_dataset import UnrealMotionDataset
from motionbricks.helper.pl_util import load_motion_rep


class DatasetContract(pl.Callback):
    """检查点携带骨架和配置契约，阻止把 G1 或其他数据集权重误用于此训练。"""

    def __init__(self, signature, kind, config):
        self.signature, self.kind, self.config = signature, kind, config

    def on_save_checkpoint(self, trainer, pl_module, checkpoint):
        checkpoint["unreal_contract"] = {"signature": self.signature, "kind": self.kind, "config": self.config}

    def on_before_backward(self, trainer, pl_module, loss):
        if not torch.isfinite(loss).all():
            raise ValueError("训练损失非有限值，请检查动作特征和训练配置")


def check_checkpoint(path, signature, kind):
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    contract = checkpoint.get("unreal_contract", {})
    if contract.get("signature") != signature or contract.get("kind") != kind:
        raise ValueError(f"{path} 与当前 UE 数据集或模型类型不匹配；不能使用 G1 权重")
    return contract


def build_config(args, dataset):
    base = Path(__file__).resolve().parents[1] / "out" / f"motionbricks_{args.model}" / "version_1" / "hparams.yaml"
    conf = OmegaConf.load(base)
    with open_dict(conf):
        conf.data = {"folder": str(Path(args.dataset).resolve()), "text_embeddings": None}
        conf.skeleton = {"_target_": "motionbricks.data.unreal_dataset.UnrealSkeleton", "folder": conf.data.folder}
        conf.motion_rep.name = "unreal_dual_root_global_joints"
        conf.motion_rep.stats.folder = str(Path(args.dataset).resolve() / "stats")
        conf.fps = dataset.manifest["fps"]
        conf.id, conf.run_dir, conf.out_dir = "unreal", str(Path(args.output).resolve()), str(Path(args.output).resolve())
        conf.trainer.max_steps = args.max_steps
        conf.model.scheduler.num_training_steps = args.max_steps
        conf.model.scheduler.num_warmup_steps = min(1000, max(0, args.max_steps // 10))
        conf.model.args.keyframe_num_warmup_steps = min(1000, max(1, args.max_steps // 10))
        if args.model == "pose":
            if not args.vqvae:
                raise ValueError("训练 Pose 必须通过 --vqvae 指定本数据集训练的 VQ-VAE")
            contract = check_checkpoint(args.vqvae, dataset.manifest["training_signature"], "vqvae")
            conf.model.pose_vqvae_network = contract["config"]["model"]["pose_vqvae_network"]
            conf.model.args.vqvae_model_ckpt_path = str(Path(args.vqvae).resolve())
            with Path(args.vqvae).open("rb") as stream:
                conf.model.args.vqvae_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        if args.tiny:
            # 仅用于 CPU 冒烟验证；模型配置会随检查点保存，不能与正式模型互换。
            if args.model == "vqvae":
                net = conf.model.pose_vqvae_network
                net.width, net.depth, net.code_dim, net.output_emb_width = 32, 1, 32, 32
                net.num_heads, net.nb_code = 2, 16
            else:
                net = conf.model.backbone_network.args
                net.n_embd, net.n_head = 32, 4
                if args.model == "pose":
                    net.n_layers = 1
                else:
                    net.n_layers_shared, net.n_layers_root_token, net.width, net.depth = 1, 1, 32, 1
    return conf


def train(args):
    if args.max_steps < 1 or args.batch_size < 1:
        raise ValueError("训练步数和批次大小必须为正数")
    pl.seed_everything(args.seed, workers=True)
    dataset = UnrealMotionDataset(args.dataset)
    signature = dataset.manifest["training_signature"]
    conf = build_config(args, dataset)
    if args.resume:
        contract = check_checkpoint(args.resume, signature, args.model)
        previous = contract["config"]
        if args.model == "pose" and previous["model"]["args"].get("vqvae_sha256") != conf.model.args.vqvae_sha256:
            raise ValueError("Pose 续训必须使用训练时的同一份 VQ-VAE 权重；相同骨架不代表码本相同")
        # 续训复用原网络结构；仅保留本次的训练步数、路径和调度器配置。
        for key in ("pose_vqvae_network", "backbone_network"):
            if key in previous["model"]:
                conf.model[key] = previous["model"][key]
    output = Path(args.output).resolve()
    if output.exists() and not args.resume:
        raise ValueError("输出目录已存在，请指定新目录或使用 --resume")
    motion_rep = load_motion_rep(conf)
    model_conf = conf.model
    pose_net = instantiate(model_conf.pose_vqvae_network, motion_rep=motion_rep.dual_rep.local_motion_rep) if model_conf.pose_vqvae_network else None
    injections = {"pose_vqvae_network": pose_net, "root_vqvae_network": None, "motion_rep": motion_rep}
    if "backbone_network" in model_conf:
        injections["backbone_network"] = instantiate(model_conf.backbone_network, motion_rep=motion_rep, _recursive_=False)
    model = instantiate(model_conf, **injections, optimizer=instantiate(model_conf.optimizer), scheduler=instantiate(model_conf.scheduler), _recursive_=False)
    if args.model == "pose":
        for parameter in pose_net.parameters():
            parameter.requires_grad_(False)
    output.mkdir(parents=True, exist_ok=True)
    # 保留 ??? 注入点；其余插值由 Hydra 在构建对应组件时解析。
    config = OmegaConf.to_container(conf, resolve=False)
    OmegaConf.save(conf, output / "config.yaml")
    checkpoint = ModelCheckpoint(dirpath=str(output / "checkpoints"), every_n_train_steps=max(1, min(1000, args.max_steps)), save_last=True, save_top_k=-1)
    trainer = pl.Trainer(max_steps=args.max_steps, accelerator=args.accelerator, devices=1, logger=CSVLogger(str(output), name="metrics"),
                         callbacks=[checkpoint, DatasetContract(signature, args.model, config)], gradient_clip_val=1.0, num_sanity_val_steps=0, log_every_n_steps=1)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=0, collate_fn=collate_batch)
    trainer.fit(model, train_dataloaders=loader, ckpt_path=args.resume)
    trainer.save_checkpoint(output / "checkpoints" / "final.ckpt")
    print(f"训练完成：{output / 'checkpoints' / 'final.ckpt'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, choices=["vqvae", "pose", "root"])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--vqvae", help="可信的本地 VQ-VAE 检查点")
    parser.add_argument("--resume", help="可信的同类模型检查点，用于恢复优化器及步数")
    parser.add_argument("--max_steps", type=int, default=10000)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--accelerator", choices=["auto", "cpu", "gpu"], default="auto")
    parser.add_argument("--tiny", action="store_true", help="使用小网络，仅用于接口和训练冒烟验证")
    train(parser.parse_args())
