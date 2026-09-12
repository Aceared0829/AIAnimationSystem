# Modified by the AIAnimationSystem maintainers: localized training documentation and command-line messages.

"""使用合成数据训练姿态模型的脚本。

无需真实动作数据集即可演示姿态骨干网络的训练流程。脚本从检查点目录
加载已保存的模型配置，并使用随机生成的动作张量进行训练。

姿态模型需要预训练 VQ-VAE 检查点，将动作编码为离散词元。
程序会自动从配置指定的路径加载 VQ-VAE 权重。

用法：
    python scripts/train_pose.py --max_steps 100
"""

import argparse
import copy
import os
from motionbricks.repository import base_weights

import pytorch_lightning as pl
import torch
from hydra.utils import instantiate
from omegaconf import DictConfig, OmegaConf, open_dict
from torch.utils.data import DataLoader

from motionbricks.data.synthetic_dataset import SyntheticMotionDataset, collate_batch
from motionbricks.helper.pl_util import load_motion_rep
from motionbricks.helper.argparse_zh import enable_chinese_argparse


def load_config(result_dir: str, max_steps: int):
    """加载 hparams.yaml，并将其调整为单 GPU 训练配置。"""
    version_dir = os.path.join(result_dir, "motionbricks_pose", "version_1")
    hparams_path = os.path.join(version_dir, "hparams.yaml")
    conf = OmegaConf.load(hparams_path)

    with open_dict(conf):
        # 将数据路径解析到保存骨架与统计量的版本目录
        conf.data = {"folder": version_dir, "text_embeddings": None}
        conf.skeleton.folder = os.path.join(version_dir, "skeleton")
        conf.motion_rep.stats.folder = os.path.join(version_dir, "stats", "motion")

        # 单 GPU 训练覆盖项
        conf.trainer.devices = 1
        conf.trainer.num_nodes = 1
        conf.trainer.max_steps = max_steps
        conf.trainer.accelerator = "auto"
        conf.trainer.strategy = "auto"
        conf.trainer.enable_progress_bar = True
        conf.trainer.log_every_n_steps = 10
        conf.trainer.val_check_interval = max_steps
        conf.trainer.num_sanity_val_steps = 0

        # 解析调度器中的 ${trainer.max_steps}
        conf.model.scheduler.num_training_steps = max_steps

        # 移除含有无法解析的 ${hydra:...} 插值的键
        conf.id = "synthetic"
        conf.run_dir = "."
        conf.out_dir = result_dir

    # 解析所有 ${} 插值，然后重新包装为 DictConfig
    resolved = OmegaConf.to_container(conf, resolve=True)
    conf = OmegaConf.create(resolved)

    return conf, version_dir


def main():
    enable_chinese_argparse()
    parser = argparse.ArgumentParser(description="姿态模型训练")
    parser.add_argument("--result_dir", type=str, default=str(base_weights()),
                        help="包含预训练检查点的目录")
    parser.add_argument("--max_steps", type=int, default=200,
                        help="训练步数")
    parser.add_argument("--batch_size", type=int, default=8,
                        help="批次大小")
    parser.add_argument("--num_samples", type=int, default=500,
                        help="数据集中的合成样本数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    pl.seed_everything(args.seed)
    conf, version_dir = load_config(args.result_dir, args.max_steps)

    # 实例化骨架和动作表示
    motion_rep = load_motion_rep(conf)
    feat_dim = len(motion_rep.indices['all'])

    # 创建合成数据集
    dataset = SyntheticMotionDataset(
        feat_dim=feat_dim,
        num_samples=args.num_samples,
        min_frames=80,
        max_frames=200,
    )
    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=2,
        collate_fn=collate_batch,
        persistent_workers=True,
    )

    # 实例化网络和模型
    model_conf = copy.deepcopy(conf.model)
    with open_dict(model_conf):
        # 实例化姿态 VQ-VAE 网络（网络将被冻结，权重由模型加载）
        pose_vqvae_net = instantiate(
            model_conf.pose_vqvae_network,
            motion_rep=motion_rep.dual_rep.local_motion_rep,
        )

        # 实例化骨干网络（访问 dual_rep 需要完整的 motion_rep）
        backbone_net = instantiate(
            model_conf.backbone_network,
            motion_rep=motion_rep,
            _recursive_=False,
        )

        # 将优化器和调度器构建为偏函数
        optimizer_fn = instantiate(model_conf.optimizer)
        scheduler_fn = instantiate(model_conf.scheduler) if model_conf.scheduler else None

        model = instantiate(
            model_conf,
            pose_vqvae_network=pose_vqvae_net,
            root_vqvae_network=None,
            backbone_network=backbone_net,
            motion_rep=motion_rep,
            optimizer=optimizer_fn,
            scheduler=scheduler_fn,
            _recursive_=False,
        )

    # 创建训练器（无需回调）
    trainer = pl.Trainer(
        max_steps=conf.trainer.max_steps,
        devices=conf.trainer.devices,
        num_nodes=conf.trainer.num_nodes,
        accelerator=conf.trainer.accelerator,
        strategy=conf.trainer.strategy,
        precision=conf.trainer.precision,
        gradient_clip_val=conf.trainer.gradient_clip_val,
        enable_progress_bar=conf.trainer.enable_progress_bar,
        log_every_n_steps=conf.trainer.log_every_n_steps,
        num_sanity_val_steps=0,
        enable_checkpointing=False,
        logger=False,
    )

    print(f"开始训练姿态模型，共 {args.max_steps} 步……")
    print(f"  特征维度：{feat_dim}")
    print(f"  批次大小：{args.batch_size}")
    print(f"  数据集大小：{args.num_samples}")
    print(f"  VQ-VAE 已加载：{model.vqvae_model_loaded}")
    trainer.fit(model, train_dataloaders=dataloader)
    print("训练完成。")


if __name__ == "__main__":
    main()
