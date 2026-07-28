import random
from typing import List, Dict, Optional, Tuple

import torch
from torch import Tensor
from torch.utils.data import Dataset


class SyntheticMotionDataset(Dataset):
    """无需完整动作数据即可训练的合成动作数据集。

    每个样本都是形状为 [T, feat_dim] 的随机张量。T 从
    [min_frames, max_frames] 中均匀采样，feat_dim 与动作表示维度一致
    （例如 G1Skeleton34 为 418）。
    """

    def __init__(
        self,
        feat_dim: int,
        num_samples: int = 1000,
        min_frames: int = 80,
        max_frames: int = 300,
    ):
        self.feat_dim = feat_dim
        self.num_samples = num_samples
        self.lengths = [
            random.randint(min_frames, max_frames) for _ in range(num_samples)
        ]

    def __len__(self):
        return self.num_samples

    def __getitem__(self, idx):
        T = self.lengths[idx]
        motion = torch.randn(T, self.feat_dim)
        return {"keyid": idx, "motion": motion}


def collate_tensors(
    tensor_batch: List[Tensor],
    size: Optional[int] = None,
) -> Tuple[Tensor, Tensor, Tensor]:
    """将长度不同的张量填充到统一长度。

    返回：
        - 填充后的动作 [B, T, D]
        - 长度 [B]
        - 填充掩码 [B, T]（有效位置为 True）
    """
    rep_dim = tensor_batch[0].shape[1]
    max_size = max(mo.shape[0] for mo in tensor_batch)
    if size is not None:
        assert size >= max_size
        max_size = size

    motion_batch = torch.zeros(len(tensor_batch), max_size, rep_dim)
    pad_mask = torch.zeros(len(tensor_batch), max_size, dtype=torch.bool)
    lengths = []
    for bi, mo in enumerate(tensor_batch):
        cur_len = mo.shape[0]
        lengths.append(cur_len)
        motion_batch[bi, :cur_len] = mo
        pad_mask[bi, :cur_len] = True

    len_batch = torch.tensor(lengths)
    return motion_batch, len_batch, pad_mask


def collate_batch(batch: List[Dict]) -> Dict:
    """将一批动作字典整理为填充后的张量。"""
    motion = [bdict["motion"] for bdict in batch]
    motion, motion_len, motion_pad_mask = collate_tensors(motion)
    return {
        "motion": motion,
        "motion_len": motion_len,
        "motion_pad_mask": motion_pad_mask,
        "batch_size": len(motion),
    }
