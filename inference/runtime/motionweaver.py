"""MotionWeaver Pose Token inference in the UE pose-relative feature space.

Schema-v2 UE motion features describe the pelvis subtree relative to the
separate authoritative Actor Root. The five-dimensional root below belongs to
that pose feature space. A CMC/Mover world trajectory must not be passed here;
``predict_with_actor_root`` uses the separately trained Actor Root condition.
"""

import hashlib
import json
from pathlib import Path

import torch
from hydra.utils import instantiate
from omegaconf import OmegaConf, open_dict

from motionbricks.helper.data_training_util import extract_feature_from_motion_rep
from motionbricks.helper.pl_util import load_motion_rep
from motionbricks.data.motionweaver_root import actor_track_to_condition
from motionbricks.motion_backbone.inference.motion_inference import motion_inference


class MotionWeaverInference(motion_inference):
    """Run MotionBricks Pose Tokens with an explicit root-condition profile."""

    def __init__(self, pose_model, args, device="cpu", condition_profile=None):
        torch.nn.Module.__init__(self)
        self._pose_model = pose_model.eval().to(device)
        self._vqvae_pose_model = pose_model.supporting_nets["pose_net"].eval().to(device)
        self.global_motion_rep = pose_model.global_motion_rep
        self.local_motion_rep = pose_model.local_motion_rep
        self.motion_rep = pose_model.motion_rep
        self._args = args
        self._device = torch.device(device)
        self.condition_profile = condition_profile
        if not (pose_model.backbone_net.initted and pose_model.vqvae_model_loaded):
            raise ValueError("Pose and VQ-VAE checkpoints must be initialized")

    @torch.no_grad()
    def predict_with_pose_root(
        self,
        pose_root_values,
        local_poses,
        has_local_poses,
        *,
        config=None,
        text_embeddings=None,
        has_text_embeddings=None,
    ):
        """Generate pose features given an unnormalized pose-relative root.

        ``pose_root_values`` has shape [B, 4*N, 5] in the model's global
        pelvis-root representation. It is not a CMC/Mover/Actor world Root.
        This is an offline oracle-root path until an Actor Root conditioning
        model is trained. ``local_poses`` and its mask use the original
        eight-frame convention: four starting and four optional ending frames.
        A live player must leave ending-frame masks false unless those poses
        come from an online source. No ground-truth future pose is fetched.
        """
        if self.condition_profile == "actor_root_history4_compact_v1":
            raise ValueError("Actor-conditioned Pose model requires predict_with_actor_root")
        config = dict(config or {})
        if pose_root_values.ndim != 3 or local_poses.ndim != 3 or has_local_poses.ndim != 2:
            raise ValueError("Expected [B,T,root], [B,8,pose], and [B,8] tensors")
        batch_size, frame_count, root_dim = pose_root_values.shape
        if batch_size != 1:
            raise ValueError("The upstream MotionBricks sampler currently supports one character per call")
        frames_per_token = self._pose_model.backbone_net.get_num_frames_per_token()
        if root_dim != len(self.global_motion_rep.indices["root"]):
            raise ValueError("Root feature dimension does not match the checkpoint")
        if frame_count == 0 or frame_count % frames_per_token:
            raise ValueError("Root horizon must contain complete pose tokens")
        num_tokens = frame_count // frames_per_token
        if num_tokens < self._args["min_tokens"]:
            raise ValueError("Root horizon is shorter than checkpoint min_tokens")
        if num_tokens > self._args["max_tokens"]:
            raise ValueError("Root horizon exceeds checkpoint max_tokens")
        if local_poses.shape[:2] != (batch_size, 2 * frames_per_token):
            raise ValueError("Pose conditions must contain starting and ending slots")
        if has_local_poses.shape != local_poses.shape[:2]:
            raise ValueError("Pose condition mask shape mismatch")
        if not has_local_poses[:, :frames_per_token].all():
            raise ValueError("Four historical pose frames are required")
        if not torch.isfinite(pose_root_values).all():
            raise ValueError("Root contains non-finite values")
        if not torch.isfinite(local_poses).all():
            raise ValueError("Pose condition contains non-finite values")

        model_dtype = next(self._pose_model.backbone_net.parameters()).dtype
        pose_root_values = pose_root_values.to(self._device, dtype=model_dtype)
        local_poses = local_poses.to(self._device, dtype=model_dtype)
        has_local_poses = has_local_poses.to(self._device, dtype=torch.bool)
        local_poses = torch.where(has_local_poses[..., None], local_poses, 0.0)

        _, _, recentered_root = self._extract_initial_root_info(pose_root_values)
        max_frames = self._args["max_tokens"] * frames_per_token
        if frame_count < max_frames:
            padding = recentered_root[:, -1:].expand(-1, max_frames - frame_count, -1)
            model_root = torch.cat((recentered_root, padding), dim=1)
        else:
            model_root = recentered_root
        normalized_root = self.global_motion_rep.normalize(model_root)
        token_count = torch.full((batch_size, 1), num_tokens, dtype=torch.int, device=pose_root_values.device)
        normalized_local_root = self.motion_rep.dual_rep.global_to_local(
            normalized_root, is_normalized=True, to_normalize=True,
            lengths=token_count * frames_per_token,
        )
        feature_indices = extract_feature_from_motion_rep(
            torch.zeros((1, 1, len(self.local_motion_rep.indices["all"])),
                        device=local_poses.device, dtype=local_poses.dtype),
            self.local_motion_rep, self.INTERNAL_POSE_FEATURE_MODE, fetch_feat_idx=True,
        )
        if local_poses.shape[-1] != len(feature_indices) - 1:
            raise ValueError("Pose feature dimension does not match the checkpoint")
        # Root height at each pose condition slot is supplied by the same root
        # sequence. This keeps the decoder condition in the original feature space.
        condition_frames = torch.cat((
            torch.arange(frames_per_token, device=local_poses.device),
            torch.arange(frame_count - frames_per_token, frame_count, device=local_poses.device),
        ))
        root_height = recentered_root[:, condition_frames][
            :, :, self.global_motion_rep.indices["global_root_pos"][[1]]
        ]
        mean = self.local_motion_rep.stats.mean[feature_indices].to(local_poses)
        std = self.local_motion_rep.stats.std[feature_indices].to(local_poses)
        normalized_pose = (torch.cat((root_height, local_poses), dim=-1) - mean) / torch.sqrt(std.square() + self.EPS)
        batch = {
            "pred_num_tokens": token_count,
            "pred_global_root_values": normalized_root,
            "pred_local_root_values": normalized_local_root,
            "local_poses": normalized_pose,
            "has_local_poses": has_local_poses.bool(),
            "text_embeddings": text_embeddings,
            "has_text_embeddings": has_text_embeddings,
        }
        batch["pred_pose_tokens"], batch["pred_pose_cond"], batch["pred_has_pose_cond"] = \
            self._predict_pose_tokens(batch, config)
        config["final_root_pred_mode"] = "from_root_module"
        batch["pred_local_poses"], batch["pred_global_poses"] = \
            self._decode_motions_from_predicted_root_and_pose_tokens(batch, config)
        global_pose = batch["pred_global_poses"][:, :frame_count].clone()
        # The decoder's direct-root mode already used the supplied heading.
        # Reapplying MotionBricks' predicted-root heading would rotate it twice.
        global_pose[:, :, self.global_motion_rep.indices["root"]] = pose_root_values
        return global_pose, batch["pred_pose_tokens"]

    def predict_with_root(self, *args, **kwargs):
        raise RuntimeError(
            "The five-dimensional root is pose-relative, not a CMC/Mover Actor Root. "
            "Use predict_with_pose_root only for an explicitly labeled offline "
            "pose-root test; Actor Root conditioning requires a trained bridge."
        )

    @torch.no_grad()
    def predict_with_actor_root(
        self, actor_root_track, pose_root_history, local_pose_history, *, config=None,
        debug_decoder_pose_root=None, allow_offline_oracle=False,
    ):
        """Generate Actor-relative pose features from an independent Actor plan.

        ``actor_root_track``: [1,T,7] world transforms in Motion metres,
        Y-up, xyzw. Its first four frames match the supplied four history
        frames; remaining frames are a controller/model plan available online.
        ``pose_root_history``: [1,4,5] pelvis root in the UE pose-relative
        feature space. ``local_pose_history``: [1,4,D] joint positions and
        rotations from the same four historical frames. The Actor transform
        remains external and must be applied once by the UE movement layer.
        The returned sequence includes those four historical frames; a live
        caller consumes new frames from index four onward.

        This path uses the VQ decoder's mean normalized external pose-root
        condition for unknown future frames. It requires visual and contact
        validation before use in a playable UE character.
        ``debug_decoder_pose_root`` replaces that condition with the true
        future pose root only for labeled offline ablations; it requires
        ``allow_offline_oracle=True`` and must never be used in live control.
        """
        if self.condition_profile != "actor_root_history4_compact_v1":
            raise ValueError("Actor Root inference requires an Actor-conditioned MotionWeaver checkpoint")
        if actor_root_track.ndim != 3 or pose_root_history.ndim != 3 or local_pose_history.ndim != 3:
            raise ValueError("Expected [1,T,7], [1,4,5], and [1,4,pose_dim]")
        frames_per_token = self._pose_model.backbone_net.get_num_frames_per_token()
        batch_size, frame_count, actor_dim = actor_root_track.shape
        if batch_size != 1 or actor_dim != 7 or frame_count % frames_per_token:
            raise ValueError("Actor Root must contain one character and complete pose tokens")
        num_tokens = frame_count // frames_per_token
        if not self._args["min_tokens"] <= num_tokens <= self._args["max_tokens"]:
            raise ValueError("Actor Root horizon is outside the checkpoint token range")
        if pose_root_history.shape != (1, frames_per_token, 5):
            raise ValueError("Pose root history must have four five-dimensional frames")
        pose_indices = extract_feature_from_motion_rep(
            None, self.local_motion_rep, self.INTERNAL_POSE_FEATURE_MODE,
            fetch_feat_idx=True,
        )
        if local_pose_history.shape != (1, frames_per_token, len(pose_indices) - 1):
            raise ValueError("Local pose history dimension does not match the checkpoint")
        if not all(torch.isfinite(value).all() for value in
                   (actor_root_track, pose_root_history, local_pose_history)):
            raise ValueError("Actor Root or pose history contains non-finite values")
        if not torch.allclose(torch.linalg.vector_norm(actor_root_track[..., 3:], dim=-1),
                              torch.ones_like(actor_root_track[..., 0]), atol=1e-3):
            raise ValueError("Actor Root quaternions must be normalized")
        if self._pose_model.args["cond_root_feature_is_from_motion_rep"] != "global" or \
                self._pose_model.args["cond_root_feature"] != "root_without_hip_height":
            raise ValueError("Actor Root profile requires global four-dimensional root conditions")

        dtype = next(self._pose_model.backbone_net.parameters()).dtype
        actor_root_track = actor_root_track.to(self._device, dtype=dtype)
        pose_root_history = pose_root_history.to(self._device, dtype=dtype)
        local_pose_history = local_pose_history.to(self._device, dtype=dtype)
        actor_condition = actor_track_to_condition(actor_root_track)
        max_frames = self._args["max_tokens"] * frames_per_token
        if frame_count < max_frames:
            padding = actor_condition[:, -1:].expand(-1, max_frames - frame_count, -1)
            actor_condition = torch.cat((actor_condition, padding), dim=1)
        actor_indices = extract_feature_from_motion_rep(
            None, self.global_motion_rep, "root_without_hip_height",
            fetch_feat_idx=True,
        )
        # This five-slot tensor is only a carrier for the upstream 4D feature
        # selector. It is not a normalized pose root and is never used as the
        # decoded character displacement.
        model_actor_root = torch.zeros((1, max_frames, 5), dtype=dtype, device=self._device)
        model_actor_root[:, :, actor_indices] = actor_condition
        # The VQ decoder was trained with a separate pose-root velocity input.
        # Unknown future pose-root velocity uses the mean in normalized space.
        decoder_pose_root = torch.zeros(
            (1, max_frames, len(self.local_motion_rep.indices["root"])),
            dtype=dtype, device=self._device,
        )
        if debug_decoder_pose_root is not None:
            if not allow_offline_oracle:
                raise ValueError("Oracle decoder condition requires an explicit offline diagnostic flag")
            if debug_decoder_pose_root.shape != (1, frame_count, 5) or not \
                    torch.isfinite(debug_decoder_pose_root).all():
                raise ValueError("Oracle pose root must have finite [1,T,5] values")
            oracle_root = debug_decoder_pose_root.to(self._device, dtype=dtype)
            if frame_count < max_frames:
                oracle_root = torch.cat((oracle_root, oracle_root[:, -1:].expand(
                    -1, max_frames - frame_count, -1)), dim=1)
            decoder_pose_root = self.motion_rep.dual_rep.global_to_local(
                self.global_motion_rep.normalize(oracle_root),
                is_normalized=True, to_normalize=True,
                lengths=torch.full((1, 1), frame_count, dtype=torch.int, device=self._device),
            )
        history_pose = torch.cat((pose_root_history[:, :, [1]], local_pose_history), dim=-1)
        mean = self.local_motion_rep.stats.mean[pose_indices].to(history_pose)
        std = self.local_motion_rep.stats.std[pose_indices].to(history_pose)
        normalized_history = (history_pose - mean) / torch.sqrt(std.square() + self.EPS)
        local_poses = torch.cat((normalized_history, torch.zeros_like(normalized_history)), dim=1)
        has_local_poses = torch.tensor([[True] * frames_per_token + [False] * frames_per_token],
                                       dtype=torch.bool, device=self._device)
        heading = torch.atan2(pose_root_history[:, 0, 4], pose_root_history[:, 0, 3])
        batch = {
            "reference_start_root_global_offsets": pose_root_history[:, :1,
                self.global_motion_rep.indices["global_root_pos_2d"]],
            "reference_start_root_global_heading": heading,
            "pred_num_tokens": torch.full((1, 1), num_tokens, dtype=torch.int, device=self._device),
            "pred_global_root_values": model_actor_root,
            "pred_local_root_values": decoder_pose_root,
            "local_poses": local_poses,
            "has_local_poses": has_local_poses,
            "text_embeddings": None,
            "has_text_embeddings": None,
        }
        config = dict(config or {})
        batch["pred_pose_tokens"], batch["pred_pose_cond"], batch["pred_has_pose_cond"] = \
            self._predict_pose_tokens(batch, config)
        config["final_root_pred_mode"] = "from_pose_module"
        batch["pred_local_poses"], batch["pred_global_poses"] = \
            self._decode_motions_from_predicted_root_and_pose_tokens(batch, config)
        return self._reapply_initial_root_info(batch)[:, :frame_count].clone(), batch["pred_pose_tokens"]


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_motionweaver_pose(pose_checkpoint, *, vqvae_checkpoint, dataset_dir=None, device="cpu"):
    """Load a UE Pose checkpoint and its exact VQ-VAE under the dataset contract.

    Both checkpoints must carry the same Unreal training signature. The Pose
    checkpoint must also name the exact VQ-VAE SHA-256 used during training.
    ``dataset_dir`` is the local copy of the corresponding prepared UE dataset.
    """
    pose_checkpoint = Path(pose_checkpoint).resolve()
    vqvae_checkpoint = Path(vqvae_checkpoint).resolve()
    pose_state = torch.load(pose_checkpoint, map_location="cpu", weights_only=False)
    pose_contract = pose_state.get("unreal_contract", {})
    if pose_contract.get("kind") != "pose":
        raise ValueError("Pose checkpoint has no UE Pose training contract")
    vqvae_state = torch.load(vqvae_checkpoint, map_location="cpu", weights_only=False)
    vqvae_contract = vqvae_state.get("unreal_contract", {})
    if vqvae_contract.get("kind") != "vqvae":
        raise ValueError("VQ-VAE checkpoint has no UE VQ-VAE training contract")
    signature = pose_contract.get("signature")
    if not signature or signature != vqvae_contract.get("signature"):
        raise ValueError("Pose and VQ-VAE checkpoints have different UE training signatures")
    if pose_contract.get("training_contract") != vqvae_contract.get("training_contract"):
        raise ValueError("Pose and VQ-VAE checkpoints have different UE training contracts")
    del vqvae_state

    conf = OmegaConf.create(pose_contract["config"])
    profile = conf.get("motionweaver_profile")
    if (conf.model._target_ != "motionbricks.motion_backbone.models.motionweaver_pose_model.MotionWeaverPoseModel"
            or profile not in {"online_history4_compact_v1", "actor_root_history4_compact_v1"}):
        raise ValueError("Pose checkpoint is not a supported MotionWeaver online-history model")
    if pose_contract.get("motionweaver_profile") != profile:
        raise ValueError("MotionWeaver checkpoint and config condition profiles differ")
    if profile == "actor_root_history4_compact_v1" and not conf.get("motionweaver_actor_root_manifest_sha256"):
        raise ValueError("Actor-conditioned Pose checkpoint lacks Actor Root training provenance")
    expected_vqvae_sha = conf.model.args.get("vqvae_sha256")
    if not expected_vqvae_sha or _sha256(vqvae_checkpoint) != expected_vqvae_sha:
        raise ValueError("VQ-VAE SHA-256 differs from the Pose training contract")
    dataset_dir = Path(dataset_dir or conf.data.folder).resolve()
    with (dataset_dir / "dataset.json").open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("training_signature") != signature:
        raise ValueError("Local dataset has a different UE training signature")
    if conf.data.get("manifest_sha256") != _sha256(dataset_dir / "dataset.json"):
        raise ValueError("Local dataset manifest differs from the Pose training dataset")
    if manifest.get("training_contract") != pose_contract.get("training_contract"):
        raise ValueError("Local dataset has a different UE training contract")
    with open_dict(conf):
        conf.data.folder = str(dataset_dir)
        conf.skeleton.folder = str(dataset_dir)
        conf.motion_rep.stats.folder = str(dataset_dir / "stats")
        conf.model.args.vqvae_model_ckpt_path = str(vqvae_checkpoint)

    motion_rep = load_motion_rep(conf)
    pose_net = instantiate(conf.model.pose_vqvae_network, motion_rep=motion_rep.dual_rep.local_motion_rep)
    backbone = instantiate(conf.model.backbone_network, motion_rep=motion_rep, _recursive_=False)
    pose_model = instantiate(
        conf.model, pose_vqvae_network=pose_net, root_vqvae_network=None,
        backbone_network=backbone, motion_rep=motion_rep,
        optimizer=None, scheduler=None, _recursive_=False,
    )
    pose_model.load_state_dict(pose_state["state_dict"], strict=True)
    del pose_state
    return MotionWeaverInference(pose_model, pose_model.args, device=device, condition_profile=profile)
