"""将 Schema v2 VQ-VAE 导出为接收 UE Root 相对姿态的固定窗口 ONNX。"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from scipy.spatial.transform import Rotation

from inference.runtime.checkpoint import load_vqvae
from motionbricks.data.unreal_dataset import UE_TO_MOTION
from motionbricks.helper.data_training_util import extract_feature_from_motion_rep
from motionbricks.motionlib.core.utils.rotations import cont6d_to_matrix


def matrix_product(left, right):
    """将骨骼和帧批次展平；DirectML 的 MatMul 不接受五维矩阵批次。"""
    batch = torch.broadcast_shapes(left.shape[:-2], right.shape[:-2])
    rows, inner, columns = left.shape[-2], left.shape[-1], right.shape[-1]
    left = left.expand(*batch, rows, inner).reshape(-1, rows, inner)
    right = right.expand(*batch, inner, columns).reshape(-1, inner, columns)
    return torch.bmm(left, right).reshape(*batch, rows, columns)


class UnrealPoseReconstruction(torch.nn.Module):
    """输入 cm 与行优先旋转矩阵；输出同一 Root 空间的姿态，不输出权威位移。"""

    def __init__(self, net, rep, skeleton, window_frames=16, pose_condition="none"):
        super().__init__()
        self.net = net
        self.frames = window_frames
        if pose_condition not in ("none", "endpoints"):
            raise ValueError("未知的姿态条件模式")
        self.pose_condition = pose_condition
        endpoint_mask = torch.zeros(1, window_frames, dtype=torch.bool)
        endpoint_mask[:, 0] = endpoint_mask[:, -1] = True
        self.register_buffer("endpoint_mask", endpoint_mask)
        self.joints = len(skeleton["bones"])
        self.fps = rep.fps
        self.parents = [b["parent"] for b in skeleton["bones"]]
        self.right_hip, self.left_hip = rep.skeleton.hip_joint_idx
        self.rotation_indices = rep.dual_rep.local_motion_rep.indices["global_rot_data"]
        self.register_buffer("basis", torch.tensor(UE_TO_MOTION, dtype=torch.float32))
        reference = Rotation.from_quat([b["rotation"] for b in skeleton["bones"]]).as_matrix()
        self.register_buffer("reference", torch.tensor(reference, dtype=torch.float32))
        self.register_buffer("neutral", rep.skeleton.neutral_joints.clone())
        stats = rep.dual_rep.local_motion_rep.stats
        self.register_buffer("mean", stats.mean.clone())
        self.register_buffer("scale", stats.std.clamp_min(.001) if stats.legacy else torch.sqrt(stats.std ** 2 + stats.eps))
        self.register_buffer("horizontal", torch.tensor([1., 0., 1.]))

    def forward(self, pose_history):
        frames, joints = self.frames, self.joints
        positions = pose_history[..., :3] @ self.basis.T * .01
        rotations = matrix_product(matrix_product(self.basis, matrix_product(pose_history[..., 3:].reshape(1, frames + 1, joints, 3, 3), self.reference.transpose(-1, -2))), self.basis.T)
        across = positions[:, 0, self.right_hip] - positions[:, 0, self.left_hip]
        angle = torch.atan2(across[:, 2], -across[:, 0])
        cosine, sine = torch.cos(angle), torch.sin(angle)
        zero, one = torch.zeros_like(cosine), torch.ones_like(cosine)
        heading = torch.stack([cosine, zero, sine, zero, one, zero, -sine, zero, cosine], -1).reshape(1, 3, 3)
        initial_position = positions[:, 0, 0] * self.horizontal
        canonical = (positions - initial_position[:, None, None]) @ heading[:, None]
        canonical_rotations = matrix_product(heading.transpose(-1, -2)[:, None, None], rotations)
        velocity = (canonical[:, 1:] - canonical[:, :-1]) * self.fps
        relative = canonical[:, :frames, 1:] - canonical[:, :frames, :1] * self.horizontal
        rotations6d = torch.cat([canonical_rotations[:, :frames, ..., 0], canonical_rotations[:, :frames, ..., 1]], -1)
        # 编码器只读取位置、旋转与骨盆高度；解码条件只读取水平速度。未使用的角速度和接触不参与网络。
        features = torch.cat([
            torch.zeros_like(velocity[:, :, 0, :1]), velocity[:, :, 0, [0, 2]], canonical[:, :frames, 0, 1:2],
            relative.reshape(1, frames, -1), rotations6d.reshape(1, frames, -1), velocity.reshape(1, frames, -1), torch.zeros_like(velocity[:, :, :4, 0])
        ], -1)
        local = (features - self.mean) / self.scale
        external = extract_feature_from_motion_rep(local, self.net.motion_rep, self.net.decoder_external_cond_feature_mode)
        tokens = self.net.encode_into_idx(local)
        # 默认掩码选择输入窗口首尾；历史或已知代理前瞻的时间边界由调用方负责。
        target = local if self.pose_condition == "endpoints" else None
        mask = self.endpoint_mask if target is not None else None
        decoded = self.net.forward_decoder(tokens, target, has_target_cond=mask, external_cond=external)["recon_state"] * self.scale + self.mean
        global_rotations = matrix_product(heading[:, None, None], cont6d_to_matrix(decoded[..., self.rotation_indices].reshape(1, frames, joints, 6)))
        displacement = torch.cat([torch.zeros_like(decoded[:, :1, 1:3]), decoded[:, :-1, 1:3] / self.fps], 1).cumsum(1)
        pelvis = torch.stack([displacement[..., 0], decoded[..., 3], displacement[..., 1]], -1) @ heading.transpose(-1, -2) + initial_position[:, None]
        positions_out = [pelvis]
        for index in range(1, joints):
            parent = self.parents[index]
            offset = self.neutral[index] - self.neutral[parent]
            positions_out.append(positions_out[parent] + (global_rotations[:, :, parent] @ offset[:, None]).squeeze(-1))
        ue_positions = torch.stack(positions_out, -2) @ self.basis * 100
        ue_rotations = matrix_product(matrix_product(matrix_product(self.basis.T, global_rotations), self.basis), self.reference)
        return torch.cat([ue_positions, ue_rotations.reshape(1, frames, joints, 9)], -1)


def pack_raw_pose(raw, skeleton):
    reference = Rotation.from_quat([bone["rotation"] for bone in skeleton["bones"]]).as_matrix()
    positions = raw["positions"] @ UE_TO_MOTION * 100
    rotations = UE_TO_MOTION.T @ raw["rotations"] @ UE_TO_MOTION @ reference
    return np.concatenate([positions, rotations.reshape(*positions.shape[:-1], 9)], -1).astype("float32")


@torch.no_grad()
def reference_forward(net, rep, skeleton, packed, pose_condition="none"):
    """使用原始训练代码独立验证包装器，避免仅比较两个相同的新实现。"""
    basis = torch.tensor(UE_TO_MOTION, dtype=torch.float32)
    reference = torch.tensor(Rotation.from_quat([b["rotation"] for b in skeleton["bones"]]).as_matrix(), dtype=torch.float32)
    count = packed.shape[1]
    positions = packed[..., :3] @ basis.T * .01
    rotations = basis @ (packed[..., 3:].reshape(1, count, len(skeleton["bones"]), 3, 3) @ reference.transpose(-1, -2)) @ basis.T
    features, initial = rep({"posed_joints": positions, "global_joint_rots": rotations}, to_normalize=True,
                            lengths=torch.tensor([count]), return_init_heading_info=True)
    local = rep.dual_rep.global_to_local(features, is_normalized=True, to_normalize=True, lengths=torch.tensor([count]))[:, :-1]
    external = extract_feature_from_motion_rep(local, net.motion_rep, net.decoder_external_cond_feature_mode)
    target, mask = None, None
    if pose_condition == "endpoints":
        target = local
        mask = torch.zeros(local.shape[:2], dtype=torch.bool)
        mask[:, 0] = mask[:, -1] = True
    decoded = net(local, target, has_target_cond=mask, external_cond=external)["recon_state"]
    recovered = rep.dual_rep.local_motion_rep.inverse(decoded, is_normalized=True, init_heading_info=initial)
    output_pos = recovered["posed_joints"] @ basis * 100
    output_rot = basis.T @ recovered["global_joint_rots"] @ basis @ reference
    return torch.cat([output_pos, output_rot.reshape(1, count - 1, len(skeleton["bones"]), 9)], -1)


def export(checkpoint, output, window_frames=16, pose_condition="none"):
    import onnx
    import onnxruntime

    if window_frames < 8 or window_frames > 64 or window_frames % 4:
        raise ValueError("窗口必须为 8 到 64 帧的四倍数")
    net, rep, contract = load_vqvae(checkpoint)
    if contract.get("training_contract") != "pose_only_root_authoritative":
        raise ValueError("只支持 Schema v2 Root 权威契约")
    if net.encoder_input_feature_mode != "joint_positions_and_rotations_and_hip_height" or net.decoder_external_cond_feature_mode != "root_without_hip_height_without_heading":
        raise ValueError("编码特征或解码条件不兼容，不能忽略参与网络的特征")
    if rep.compute_kwargs.get("removing_heading") or rep.compute_kwargs.get("using_smooth_root"):
        raise ValueError("只支持当前非平滑 Root、保留朝向的动作表示")
    dataset = Path(contract["config"]["data"]["folder"])
    skeleton = json.loads((dataset / "skeleton.json").read_text(encoding="utf8"))
    dataset_manifest = json.loads((dataset / "dataset.json").read_text(encoding="utf8"))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    wrapper = UnrealPoseReconstruction(net, rep, skeleton, window_frames, pose_condition).eval()
    selected = []
    for category in ("Walk", "Run", "Crouch", "Jump", "Traversal", "Idle"):
        item = next(x for x in dataset_manifest["clips"] if x["split"] == "test" and x["labels"]["category"] == category and x["source_frames"] >= window_frames)
        selected.append(item)
    inputs, expected, comparisons = [], [], []
    with torch.no_grad():
        for item in selected:
            with np.load(dataset / item["raw_file"]) as raw:
                packed = pack_raw_pose(raw, skeleton)
            # 与实时节点一致：过去窗口加一帧末帧复制，不读取未来姿态。
            sample = torch.from_numpy(np.concatenate([packed[:window_frames], packed[window_frames - 1:window_frames]])[None])
            actual = wrapper(sample)
            reference = reference_forward(net, rep, skeleton, sample, pose_condition)
            error = float((actual - reference).abs().max())
            if error > .002 or not torch.isfinite(actual).all():
                raise ValueError(f"原训练实现与导出包装器不一致：{item['asset']}，最大误差 {error}")
            inputs.append(sample.numpy())
            expected.append(reference.numpy())
            comparisons.append({"asset": item["asset"], "category": item["labels"]["category"], "reference_max_abs_error": error})
        torch.onnx.register_custom_op_symbolic("aten::lift_fresh", lambda graph, tensor: tensor, 17)
        torch.onnx.export(wrapper, (torch.from_numpy(inputs[0]),), str(output / "model.onnx"), input_names=["pose_history"],
                          output_names=["reconstructed_pose"], opset_version=17, dynamo=False)
    onnx.checker.check_model(str(output / "model.onnx"))
    session = onnxruntime.InferenceSession(str(output / "model.onnx"), providers=["CPUExecutionProvider"])
    for index, (sample, reference) in enumerate(zip(inputs, expected)):
        actual = session.run(None, {"pose_history": sample})[0]
        error = float(np.max(np.abs(actual - reference)))
        if error > .01 or not np.isfinite(actual).all():
            raise ValueError(f"ONNX 数值校验失败：{error}")
        comparisons[index]["onnx_max_abs_error"] = error
    np.concatenate(inputs).astype("<f4").tofile(output / "validation_inputs.bin")
    np.concatenate(expected).astype("<f4").tofile(output / "validation_expected.bin")
    manifest = {
        "format": "ai_animation_ue_pose_onnx_v1", "purpose": "vq_reconstruction", "training_contract": contract["training_contract"],
        "training_signature": contract["signature"], "checkpoint_sha256": hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest(),
        "onnx_sha256": hashlib.sha256((output / "model.onnx").read_bytes()).hexdigest(), "training_steps": contract["global_step"],
        "window_frames": window_frames, "fps": rep.fps, "num_bones": wrapper.joints, "root_bone": skeleton["root_bone"],
        "pose_condition": pose_condition,
        "input_shape": [1, window_frames + 1, wrapper.joints, 12], "output_shape": [1, window_frames, wrapper.joints, 12],
        "layout": "root-relative UE cm xyz followed by row-major 3x3 rotation", "bones": skeleton["bones"], "validation": comparisons,
        "limitations": ["重建已知姿态，不是 Pose 条件生成。", "固定窗口使用末帧复制；边界质量需要实测。", "ONNX CPU 只用于导出数值校验，UE 使用 DirectML GPU。"]
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--window_frames", type=int, default=16)
    parser.add_argument("--pose-condition", choices=("none", "endpoints"), default="none")
    args = parser.parse_args()
    torch.set_num_threads(4)
    result = export(args.checkpoint, args.output, args.window_frames, args.pose_condition)
    print(json.dumps({"output": args.output, "training_steps": result["training_steps"], "validation": result["validation"]}, ensure_ascii=False, indent=2))
