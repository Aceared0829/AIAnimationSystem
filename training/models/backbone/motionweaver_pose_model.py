"""MotionWeaver Pose Token training with conditions available to a live player.

The motion clip still supplies target tokens and a teacher root trajectory. Only
the first four pose frames are exposed as pose conditions. Future clip poses
remain targets and are never copied into the conditioning tensor.
"""

import torch

from motionbricks.helper.data_training_util import extract_feature_from_motion_rep
from motionbricks.data.motionweaver_root import actor_track_to_condition
from motionbricks.motion_backbone.models.pose_model import MotionModel


class MotionWeaverPoseModel(MotionModel):
    """Preserve MotionBricks' token predictor with online-safe pose conditions."""

    def _root_condition_values(self, batch, sample_info, original_global_motions, first_frame_heading_angle):
        if self.backbone_net._args["local_root_dim"] != 4:
            raise ValueError("MotionWeaver Actor Root condition must have four features")
        chosen_ids = sample_info["chosen_ids"]
        start_indices = sample_info["start_indices"]
        frame_count = batch["global_motions"].shape[1]
        tracks = batch["actor_root_track"][chosen_ids]
        indices = start_indices[:, None] + torch.arange(frame_count, device=tracks.device)[None, :]
        actor_window = tracks.gather(1, indices[:, :, None].expand(-1, -1, 7))
        if not torch.all(indices[:, 0] == start_indices):
            raise AssertionError("Actor Root and pose window start frames differ")

        raw_body = self.global_motion_rep.unnormalize(original_global_motions)
        _, body_yaw = self.global_motion_rep.compute_root_pos_and_rot(
            raw_body, return_quat=False, return_angle=True
        )
        target_yaw = torch.as_tensor(first_frame_heading_angle, dtype=body_yaw.dtype, device=body_yaw.device)
        corrective_yaw = target_yaw - body_yaw[:, 0]
        actor_condition = actor_track_to_condition(actor_window, corrective_yaw)
        if actor_condition.shape != (len(chosen_ids), frame_count, 4):
            raise AssertionError("Actor Root condition and pose target windows differ")
        return actor_condition

    def _sample_the_local_pose_conditions(self, local_motions, num_frames, text_embedding=None):
        if text_embedding is not None:
            raise ValueError("MotionWeaver online pose training does not use offline text embeddings")
        history_frames = self.backbone_net.get_num_frames_per_token()
        if num_frames <= history_frames:
            raise ValueError("MotionWeaver requires future target frames after the pose history")
        poses = extract_feature_from_motion_rep(
            local_motions, self.local_motion_rep, self._args["local_pose_feature"]
        )
        conditions = torch.zeros_like(poses)
        conditions[:, :history_frames] = poses[:, :history_frames]
        has_conditions = torch.zeros(poses.shape[:2], dtype=torch.bool, device=poses.device)
        has_conditions[:, :history_frames] = True
        return conditions, has_conditions, None, None
