"""评估、推理和训练边界的 PR 回归。"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch
from omegaconf import OmegaConf

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from evaluate_unreal_vqvae import load_vqvae
from export_unreal_inference import load_package
from export_native_gallery import export
from train_unreal import training_indices
from motionbricks.data.unreal_dataset import training_signature


class ReviewRegressions(unittest.TestCase):
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
