"""验证 UE 坐标、参考骨轴、骨架边界和预处理到训练张量的契约。"""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch
from scipy.spatial.transform import Rotation

from motionbricks.data.unreal_dataset import UE_TO_MOTION, UnrealMotionDataset, UnrealSkeleton, convert_clip, derive_motion_labels, validate_clip


def fixture():
    names = ["pelvis", "thigh_l", "foot_l", "ball_l", "thigh_r", "foot_r", "ball_r"]
    parents = [-1, 0, 1, 2, 0, 4, 5]
    positions = np.array([[0, 0, 100], [0, -10, 90], [0, -10, 5], [15, -10, 0], [0, 10, 90], [0, 10, 5], [15, 10, 0]], dtype=float)
    refs = Rotation.from_euler("xyz", np.arange(21).reshape(7, 3) * 0.02).as_matrix()
    bones = [{"name": name, "parent": parent, "position": pos.tolist(), "rotation": Rotation.from_matrix(rot).as_quat().tolist()}
             for name, parent, pos, rot in zip(names, parents, positions, refs)]
    frames = []
    for frame in range(100):
        yaw = Rotation.from_euler("z", frame * 0.003).as_matrix()
        translations = positions @ yaw.T + np.array([frame * 0.5, 0, 0])
        quats = Rotation.from_matrix(yaw @ refs).as_quat()
        frames.append(np.concatenate([translations, quats], axis=-1).tolist())
    return {"schema_version": 1, "asset": "/Game/Test.Walk", "skeleton": "/Game/Test.Skeleton", "coordinate_system": "unreal_component_cm_xyzw",
            "fps": 30, "bones": bones, "frames": frames,
            "roles": {"left_hip": "thigh_l", "right_hip": "thigh_r", "left_foot": "foot_l", "left_toe": "ball_l", "right_foot": "foot_r", "right_toe": "ball_r"}}


def prepare_function():
    path = Path(__file__).resolve().parents[1] / "scripts" / "prepare_unreal_dataset.py"
    spec = importlib.util.spec_from_file_location("prepare_unreal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare


class UnrealDatasetTests(unittest.TestCase):
    def test_coordinate_and_reference_axes(self):
        positions, rotations, neutral = convert_clip(fixture())
        np.testing.assert_allclose(positions[0, 0], [0, 1, 0])
        np.testing.assert_allclose(positions[20, 0], [0, 1, 0.1], atol=1e-6)
        np.testing.assert_allclose(rotations[0], np.tile(np.eye(3), (7, 1, 1)), atol=1e-6)
        expected = UE_TO_MOTION @ Rotation.from_euler("z", 0.06).as_matrix() @ UE_TO_MOTION.T
        np.testing.assert_allclose(rotations[20, 3], expected, atol=1e-6)
        np.testing.assert_allclose(neutral[0], 0)

    def test_preserve_animated_nonroot_translation(self):
        clip = fixture()
        clip["frames"][10][2][0] += 5
        positions, _, _ = convert_clip(clip)
        self.assertGreater(positions[10, 2, 2] - positions[9, 2, 2], 0.04)

    def test_virtual_bones_are_not_part_of_training_skeleton(self):
        clip = fixture()
        clip["bones"].append({"name": "VB hand_l_prop_01", "parent": 2, "position": [0, 0, 0], "rotation": [0, 0, 0, 1]})
        for frame in clip["frames"]:
            frame.append([0, 0, 0, 0, 0, 0, 1])
        positions, rotations, _ = convert_clip(clip)
        self.assertEqual(positions.shape[1], 7)
        self.assertEqual(rotations.shape[1], 7)

    def test_asset_path_generates_chinese_text_and_stable_tags(self):
        labels = derive_motion_labels("/Game/Characters/UEFN_Mannequin/Animations/Crouch/M_Neutral_Crouch_Turn_L.M_Neutral_Crouch_Turn_L", 12)
        self.assertEqual(labels["category"], "Crouch")
        self.assertEqual(labels["action"], "crouch")
        self.assertEqual(labels["style"], "neutral")
        self.assertEqual(labels["phase"], "turn")
        self.assertIn("action:crouch", labels["tags"])
        self.assertIn("role:pose_anchor", labels["tags"])
        self.assertIn("下蹲", labels["description_zh"])
        transition = derive_motion_labels("/Game/Characters/UEFN_Mannequin/Animations/Walk/M_Neutral_Transition_Run_to_Walk.M_Neutral_Transition_Run_to_Walk")
        self.assertEqual(transition["action"], "walk")

    def test_reject_bad_topology_and_quaternion(self):
        for mutate in (lambda c: c["bones"][1].update(parent=2), lambda c: c["frames"][0][0].__setitem__(6, 0)):
            clip = fixture()
            mutate(clip)
            with self.assertRaises(ValueError):
                validate_clip(clip)

    def test_labels_use_complete_tokens(self):
        labels = derive_motion_labels("/Game/Animations/AimOffset/M_AO_FL.M_AO_FL")
        self.assertEqual(labels["phase"], "full")
        self.assertEqual(labels["direction"], "forward_and_left")

    def test_padding_has_no_loss_gradient(self):
        import torch
        from motionbricks.data.unreal_quality import masked_mean
        values = torch.tensor([[[1.], [2.], [100.]]], requires_grad=True)
        loss = masked_mean(values, torch.tensor([[True, True, False]]))
        loss.backward()
        self.assertEqual(loss.item(), 1.5)
        self.assertEqual(values.grad[0, 2, 0].item(), 0.)

    def test_native_timestamps_and_train_only_statistics(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            def named_clip(bucket):
                for suffix in range(1000):
                    name = f"/Game/Animations/Walk/Family{chr(65 + suffix // 26)}{chr(65 + suffix % 26)}"
                    if int(hashlib.sha256(name.lower().encode()).hexdigest()[:8], 16) % 10 == bucket:
                        clip = fixture()
                        clip["asset"] = name
                        clip["fps"] = 60
                        clip["timestamps_seconds"] = (np.arange(len(clip["frames"])) / 60).tolist()
                        return clip
            train_clip, test_clip = named_clip(5), named_clip(0)
            for frame in test_clip["frames"]:
                for joint in frame:
                    joint[2] += 1000
            (source / "train.json").write_text(json.dumps(train_clip), encoding="utf8")
            (source / "test.json").write_text(json.dumps(test_clip), encoding="utf8")
            (source / "manifest.json").write_text(json.dumps({"schema_version": 1, "clips": ["train.json", "test.json"]}), encoding="utf8")
            output = Path(temp) / "split"
            result = prepare_function()(source, output, split=True, native_fps=60)
            self.assertEqual([item["split"] for item in result["clips"]], ["train", "test"])
            with np.load(output / result["clips"][0]["raw_file"]) as raw:
                np.testing.assert_array_equal(raw["timestamps"], train_clip["timestamps_seconds"])
            (source / "manifest.json").write_text(json.dumps({"schema_version": 1, "clips": ["train.json"]}), encoding="utf8")
            reference = Path(temp) / "train_only"
            prepare_function()(source, reference)
            np.testing.assert_array_equal(np.load(output / "stats/mean.npy"), np.load(reference / "stats/mean.npy"))
            np.testing.assert_array_equal(np.load(output / "stats/std.npy"), np.load(reference / "stats/std.npy"))

    def test_prepare_and_read_training_data(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            (source / "manifest.json").write_text(json.dumps({"schema_version": 1, "clips": ["clip.json"]}), encoding="utf-8")
            (source / "clip.json").write_text(json.dumps(fixture()), encoding="utf-8")
            output = Path(temp) / "prepared"
            manifest = prepare_function()(source, output)
            dataset = UnrealMotionDataset(output)
            self.assertEqual(manifest["feature_dim"], 90)  # 7 * 12 + 6
            self.assertEqual(dataset[0]["motion"].shape[1], 90)
            self.assertEqual(dataset[0]["labels"]["action"], "walk")
            self.assertTrue(np.isfinite(dataset[0]["motion"].numpy()).all())
            from motionbricks.motionlib.core.motion_reps.dual_root_global_joints import GlobalRootGlobalJoints
            from motionbricks.motionlib.core.utils.stats import Stats
            representation = GlobalRootGlobalJoints(fps=30, skeleton=UnrealSkeleton(output), name="unreal_dual_root_global_joints", stats=Stats(output / "stats"))
            restored = representation.inverse(dataset[0]["motion"], is_normalized=True, return_quat=False)
            positions, rotations, _ = convert_clip(fixture())
            np.testing.assert_allclose(restored["posed_joints"].numpy(), positions, atol=1e-5)
            np.testing.assert_allclose(restored["global_joint_rots"].numpy(), rotations, atol=1e-5)
            with self.assertRaises(FileExistsError):
                prepare_function()(source, output)
            np.save(output / "stats" / "mean.npy", np.zeros(94, dtype=np.float32))
            with self.assertRaisesRegex(ValueError, "统计量"):
                UnrealMotionDataset(output)

    def test_prepare_holds_short_clip_for_pose_anchor_training(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            short = fixture()
            short["frames"] = short["frames"][:12]
            (source / "manifest.json").write_text(json.dumps({"schema_version": 1, "clips": ["short.json"]}), encoding="utf-8")
            (source / "short.json").write_text(json.dumps(short), encoding="utf-8")
            output = Path(temp) / "prepared"
            manifest = prepare_function()(source, output, short_clip_policy="hold")
            self.assertEqual(manifest["held_short_clips"], 1)
            self.assertEqual(manifest["clips"][0]["source_frames"], 12)
            self.assertEqual(manifest["clips"][0]["frames"], 65)
            self.assertEqual(len(UnrealMotionDataset(output)[0]["motion"]), 65)

    def test_mixed_skeleton_does_not_publish_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            first = fixture()
            second = copy.deepcopy(first)
            second["fps"] = 60
            for name, value in (("a.json", first), ("b.json", second)):
                (source / name).write_text(json.dumps(value), encoding="utf-8")
            (source / "manifest.json").write_text(json.dumps({"schema_version": 1, "clips": ["a.json", "b.json"]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "不一致"):
                prepare_function()(source, source / "output")
            self.assertFalse((source / "output" / "dataset.json").exists())


if __name__ == "__main__":
    unittest.main()
