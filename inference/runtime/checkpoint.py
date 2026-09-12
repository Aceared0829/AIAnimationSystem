"""Load a contract-validated VQ-VAE without the training or plotting entrypoints."""
from pathlib import Path
import torch
from hydra.utils import instantiate
from omegaconf import OmegaConf
from motionbricks.data.unreal_dataset import training_signature
from motionbricks.helper.pl_util import load_motion_rep


def load_vqvae(checkpoint_path):
    checkpoint_path = Path(checkpoint_path).resolve()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint.get("unreal_contract", {}).get("kind") != "vqvae":
        raise ValueError("检查点不是受 UE 数据契约保护的 VQ-VAE")
    conf = OmegaConf.create(checkpoint["unreal_contract"]["config"])
    if training_signature(conf.data.folder) != checkpoint["unreal_contract"]["signature"]:
        raise ValueError("检查点引用的骨架或统计量已改变")
    if Path(conf.skeleton.folder).resolve() != Path(conf.data.folder).resolve() or Path(conf.motion_rep.stats.folder).resolve() != (Path(conf.data.folder) / "stats").resolve():
        raise ValueError("检查点骨架和统计量路径必须属于同一数据集")
    motion_rep = load_motion_rep(conf)
    pose_net = instantiate(conf.model.pose_vqvae_network, motion_rep=motion_rep.dual_rep.local_motion_rep)
    prefix = "pose_net."
    state = {key[len(prefix):]: value for key, value in checkpoint["state_dict"].items() if key.startswith(prefix)}
    pose_net.load_state_dict(state, strict=True)
    pose_net.eval()
    return pose_net, motion_rep, {**checkpoint["unreal_contract"], "global_step": checkpoint.get("global_step")}
