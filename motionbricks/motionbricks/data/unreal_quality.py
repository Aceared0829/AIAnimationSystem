"""UE 原生时间训练：补齐帧仅作网络上下文，不参与重建及运动监督。"""

import numpy as np
import torch
from torch.nn import functional as F

from motionbricks.data.synthetic_dataset import collate_batch
from motionbricks.helper.data_training_util import extract_feature_from_motion_rep, sample_keyframes
from motionbricks.vqvae.models.motion_vqvae import MotionVQVAEModel
from torch.utils.data import Sampler
from collections import Counter
import math


class PoseAwareBatchSampler(Sampler):
    """按真实长度分桶，减少短姿态补齐；适度提高困难类别的抽样权重。"""

    def __init__(self, items, batch_size):
        self.batch_size = batch_size
        self.num_batches = math.ceil(len(items) / batch_size)
        counts = Counter(item["labels"]["category"] for item in items)
        buckets = {}
        for index, item in enumerate(items):
            length = item["source_frames"]
            bucket = next((limit for limit in (16, 32, 64) if length <= limit), 128)
            category = item["labels"]["category"]
            weight = (1.5 if category in {"Ragdoll", "Interactions", "Traversal"} else 1.0) / counts[category] ** 0.5
            buckets.setdefault(bucket, []).append((index, weight))
        self.buckets = list(buckets.values())
        self.bucket_weights = torch.tensor([sum(weight for _, weight in b) for b in self.buckets], dtype=torch.double)

    def __len__(self):
        return self.num_batches

    def __iter__(self):
        for _ in range(self.num_batches):
            bucket = self.buckets[int(torch.multinomial(self.bucket_weights, 1))]
            weights = torch.tensor([weight for _, weight in bucket], dtype=torch.double)
            yield [bucket[i][0] for i in torch.multinomial(weights, self.batch_size, replacement=True).tolist()]


def collate_native(batch):
    result = collate_batch(batch)
    result["valid_frames"] = torch.tensor([item["valid_frames"] for item in batch])
    return result


def masked_mean(value, mask):
    while mask.ndim < value.ndim:
        mask = mask.unsqueeze(-1)
    return (value * mask).sum() / mask.expand_as(value).sum().clamp_min(1)


def sample_native_segment(motion, length, frames):
    """包含最后合法窗口；末端额外导数上下文保持末帧，不越界读取。"""
    start = int(np.random.randint(max(1, length - frames + 1)))
    ids = torch.arange(frames + 1, device=motion.device) + start
    return motion[ids.clamp_max(length - 1)], ids[:frames] < length


class UnrealQualityVQVAE(MotionVQVAEModel):
    """独立 UE 训练入口，保留上游训练行为供旧模型复现。"""

    def training_step(self, batch, batch_idx):
        source = batch["motion"]
        lengths = batch["valid_frames"]
        frames = int(np.random.randint(self.args["min_tokens"], self.args["max_tokens"] + 1)) * self.get_num_frames_per_code()
        if self.args.get("pose_aware_sampling", False):
            frames = min(frames, max(4, math.ceil(int(lengths.min()) / 4) * 4))
        segments, masks = [], []
        for _ in range(int(self.args["batchsize_mul_factor"])):
            for index, length in enumerate(lengths.tolist()):
                segment, mask = sample_native_segment(source[index], length, frames)
                segments.append(segment)
                masks.append(mask)
        global_motion = torch.stack(segments)
        mask = torch.stack(masks)
        # 旋转增强保留真实采样间隔和动作时长。
        global_motion = self.global_motion_rep.change_first_heading(global_motion, torch.rand(len(segments), device=source.device) * 2 * np.pi,
                                                                   is_normalized=True, to_normalize=True)
        local = self.motion_rep.dual_rep.global_to_local(global_motion, is_normalized=True, to_normalize=True,
                                                       lengths=torch.full((len(segments),), frames + 1, device=source.device))[:, :frames]
        probabilities, _ = self._construct_keyframe_prob()
        max_keyframes = min(frames, self.args["pose_vqvae_max_num_keyframes"])
        probabilities = probabilities[:max_keyframes + 1]
        probabilities = probabilities / probabilities.sum()
        has_cond, cond = sample_keyframes(local, max_keyframes, probabilities)
        has_cond = has_cond & mask
        cond = cond * has_cond[..., None]
        external = extract_feature_from_motion_rep(local, self.local_motion_rep, self.pose_net.decoder_external_cond_feature_mode)
        result = self.pose_net(local, target_cond=cond, has_target_cond=has_cond, external_cond=external)
        predicted = result["recon_state"]
        recon_loss = masked_mean(F.smooth_l1_loss(predicted, local, reduction="none"), mask)
        reference = self.local_motion_rep.inverse(local, is_normalized=True, joint_positions_from="ric_data", return_all=False)
        decoded = self.local_motion_rep.inverse(predicted, is_normalized=True, return_all=False)
        gt, pred = reference["posed_joints"], decoded["posed_joints"]
        relative_gt, relative_pred = gt - gt[:, :, :1], pred - pred[:, :, :1]
        pose_loss = masked_mean(F.smooth_l1_loss(relative_pred, relative_gt, reduction="none", beta=0.05), mask)
        root_loss = masked_mean(F.smooth_l1_loss(pred[:, :, 0], gt[:, :, 0], reduction="none", beta=0.05), mask)
        fidx = self.motion_rep.skeleton.foot_joint_idx
        endpoint_loss = masked_mean(F.smooth_l1_loss(relative_pred[:, :, fidx], relative_gt[:, :, fidx], reduction="none", beta=0.05), mask)
        pair_mask = mask[:, 1:] & mask[:, :-1]
        velocity_loss = masked_mean(F.smooth_l1_loss(torch.diff(pred, dim=1) * self.motion_rep.fps,
                                                    torch.diff(gt, dim=1) * self.motion_rep.fps, reduction="none"), pair_mask)
        # 接触状态来自参考动作，模型不能靠预测“不接触”逃避滑步惩罚。
        contact = reference["foot_contacts"][:, :-1].detach().clamp(0, 1)
        foot_speed = torch.linalg.vector_norm(torch.diff(pred[:, :, fidx], dim=1) * self.motion_rep.fps, dim=-1)
        contact_loss = masked_mean(foot_speed, contact * pair_mask[..., None])
        geometry = self.args.get("ue_geometry_coeff", 1.0)
        loss = recon_loss + self.args["commit_loss_coeff"] * result["l_commit"]
        loss = loss + geometry * (pose_loss + root_loss + 0.5 * endpoint_loss + 0.05 * velocity_loss + 0.005 * contact_loss)
        for key, value in {"loss": loss, "recon": recon_loss, "pose_m": pose_loss, "root_m": root_loss, "feet_m": endpoint_loss,
                           "velocity": velocity_loss, "contact": contact_loss, "perplexity": result["perplexity"]}.items():
            self.log(f"loss/train_{key}", value, on_step=True, on_epoch=False, batch_size=len(segments))
        return loss
