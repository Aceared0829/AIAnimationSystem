"""评估、推理和训练边界的 PR 回归。"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import hashlib
from unittest.mock import patch

import numpy as np
import torch

from training.evaluation.evaluate_unreal_vqvae import load_vqvae, preview_timing
from training.evaluation.evaluate_native_quality import select_evaluation_indices, verify_same_partition
from inference.export.export_unreal_inference import load_package
from training.evaluation.export_native_gallery import export
from training.pretrain.train_unreal import training_indices
from motionbricks.data.unreal_dataset import training_signature, file_sha256
from motionbricks.training.unreal_quality import sample_native_segment
from test_unreal_dataset import fixture, prepare_function


class ReviewRegressions(unittest.TestCase):
    def test_holdout_selection_never_includes_training_clips(self):
        manifest = {"clips": [
            {"split": "train", "labels": {"category": "Traversal"}},
            {"split": "validation", "labels": {"category": "Traversal"}},
            {"split": "test", "labels": {"category": "Traversal"}},
            {"split": "validation", "labels": {"category": "Walk"}},
        ]}
        self.assertEqual(select_evaluation_indices(manifest, "holdout", ["Traversal"]), [1, 2])

    def test_partition_verification_allows_label_only_manifest_changes(self):
        current = {"clips": [{"asset": "/Game/A", "split": "validation", "labels": {"motion": {"speed": 1}}}]}
        baseline = {"clips": [{"asset": "/Game/A", "split": "validation"}]}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "dataset.json").write_text(json.dumps(baseline), encoding="utf8")
            verified, method = verify_same_partition(current, {"config": {"data": {"folder": str(folder)}}}, "different")
        self.assertTrue(verified)
        self.assertEqual(method, "asset_split_map")

    def test_last_native_window_includes_last_real_frame(self):
        motion = torch.arange(9)[:, None]
        with patch("numpy.random.randint", side_effect=lambda high: high - 1):
            segment, mask = sample_native_segment(motion, 9, 8)
        self.assertEqual(segment[:, 0].tolist(), [1, 2, 3, 4, 5, 6, 7, 8, 8])
        self.assertTrue(mask.all())
        segment, mask = sample_native_segment(motion[:2], 2, 4)
        self.assertEqual(segment[:, 0].tolist(), [0, 1, 1, 1, 1])
        self.assertEqual(mask.tolist(), [True, True, False, False])

    def test_large_file_digest_matches_standard_hash(self):
        payload = b"test" * 700000
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weights"
            path.write_bytes(payload)
            self.assertEqual(file_sha256(path), hashlib.sha256(payload).hexdigest())

    def test_gif_subsampling_preserves_source_duration(self):
        ids, durations = preview_timing(120, 60, 10)
        self.assertEqual(ids[0], 0)
        self.assertEqual(ids[-1], 119)
        self.assertAlmostEqual(float(durations.sum()), 2000.)
        np.testing.assert_allclose(durations[:-1], np.diff(ids) * 1000 / 60)

    def test_native_time_rejects_shifted_axis_and_missing_last_key(self):
        for shifted, missing_end in [(True, False), (False, True)]:
            with self.subTest(shifted=shifted), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                clip = fixture()
                clip["sampling_policy"] = "source_data_keys"
                clip["timestamps_seconds"] = (np.arange(100) / 30 + (1 if shifted else 0)).tolist()
                clip["duration_seconds"] = (100 if missing_end else 99) / 30
                (root / "clip.json").write_text(json.dumps(clip))
                (root / "manifest.json").write_text(json.dumps({"schema_version": 1, "clips": ["clip.json"]}))
                with self.assertRaises(ValueError):
                    prepare_function()(root, root / "output")
                self.assertFalse((root / "output/dataset.json").exists())

    def test_all_models_respect_holdout_partition(self):
        manifest = {"split_policy": "asset_family_sha256_80_10_10", "clips": [{"split": s} for s in ["test", "train", "validation"]]}
        self.assertEqual(training_indices(manifest), [1])
        manifest["clips"].pop(1)
        with self.assertRaisesRegex(ValueError, "训练分区"):
            training_indices(manifest)
        manifest["split_policy"] = "none"
        self.assertEqual(training_indices(manifest), [0, 1])

    def test_changed_statistics_are_rejected_before_model_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stats").mkdir()
            (root / "skeleton.json").write_text("{}")
            for name in ["mean", "std"]:
                np.save(root / "stats" / f"{name}.npy", np.zeros(4))
            signature = training_signature(root)
            contract = {"kind": "vqvae", "signature": signature, "config": {"data": {"folder": str(root)}}}
            torch.save({"unreal_contract": contract}, root / "model.ckpt")
            (root / "manifest.json").write_text(json.dumps({"signature": signature}))
            np.save(root / "stats/mean.npy", np.ones(4))
            with self.assertRaisesRegex(ValueError, "统计量"):
                load_vqvae(root / "model.ckpt")
            with self.assertRaisesRegex(ValueError, "统计量"):
                load_package(root)

    def test_gallery_without_baseline_does_not_invent_run_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = {"category": "Poses", "frames": 12, "new": {"pose_rmse_cm": 1.}}
            report = {"fps": 24, "split": "test", "training_steps": 17, "pose_aware_sampling": True,
                      "sample_count": 1, "samples": [sample], "aggregate": {"new": sample["new"]}}
            source = root / "gallery.json"
            source.write_text(json.dumps({"report": report, "previews": [{"name": "test"}], "parents": [-1]}))
            export([source], root / "report.html")
            html = (root / "report.html").read_text(encoding="utf8")
            self.assertIn("无基线", html)
            self.assertNotIn("1,728", html)
            self.assertNotIn("20,000", html)
            self.assertNotIn("RTX 4070", html)
            self.assertNotIn("__PAYLOAD__", html)
            report["samples"][0]["old"] = {"pose_rmse_cm": .5}
            source.write_text(json.dumps({"report": report, "previews": [{"name": "test"}], "parents": [-1]}))
            export([source], root / "report.html")
            self.assertIn("1 / 1 段姿态误差上升", (root / "report.html").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
