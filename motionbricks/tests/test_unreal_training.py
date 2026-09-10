"""用刚性动画夹具执行小网络训练、检查点衔接和续训；不评估生成质量。"""

import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import torch

from test_unreal_dataset import fixture, pose_only_fixture, prepare_function


class UnrealTrainingTests(unittest.TestCase):
    def test_negative_endpoint_weight_is_rejected(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "train_unreal.py"
        result = subprocess.run([sys.executable, str(script), "--model", "vqvae", "--dataset", "unused", "--output", "unused",
                                 "--hand_endpoint_coeff", "-0.1"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ValueError", result.stderr)

    def test_pose_only_dataset_rejects_root_training(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "train_unreal.py"
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source"
            source.mkdir()
            (source / "manifest.json").write_text(json.dumps({"schema_version": 2, "training_contract": "pose_only_root_authoritative", "clips": ["clip.json"]}), encoding="utf-8")
            (source / "clip.json").write_text(json.dumps(pose_only_fixture()), encoding="utf-8")
            dataset = folder / "data"
            prepare_function()(source, dataset)
            result = subprocess.run([sys.executable, str(script), "--model", "root", "--dataset", str(dataset), "--output", str(folder / "root"), "--max_steps", "1", "--tiny"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Root", result.stderr)

    def test_pose_low_focus_probability_has_finite_loss(self):
        from motionbricks.motion_backbone.models.pose_model import MotionModel

        model = SimpleNamespace(backbone_net=SimpleNamespace(get_num_heads=lambda: (2, 0)),
                                _args={"incorrect_token_ratio_min": 0.0, "incorrect_token_ratio_max": 1.0, "masked_token_ratio": 0.8})
        tokens = torch.zeros(1, 6, 2, dtype=torch.long)
        # 合法的极低采样概率原先会使所有监督目标都被忽略。
        with patch("torch.cos", return_value=torch.full((1, 1), 0.001)):
            focused, masked, incorrect, correct, *_ = MotionModel._get_token_masks(model, {"groundtruth_pose_tokens": tokens})
        self.assertTrue(focused.any(dim=-1).all())
        self.assertTrue(torch.equal(focused, masked | incorrect | correct))
        logits = torch.zeros(1, 6, 2, 4, requires_grad=True)
        loss = MotionModel.loss(model, {"groundtruth_pose_tokens": tokens, "focused_token_mask": focused}, {"pose_logits": logits})["loss"]
        self.assertTrue(torch.isfinite(loss))
        loss.backward()
        self.assertTrue(torch.isfinite(logits.grad).all())
        self.assertGreater(logits.grad.abs().sum().item(), 0)

    def test_resumed_schedule_uses_extended_horizon(self):
        from motionbricks.motionlib.train.scheduler import WarmupCosineScheduler

        script = Path(__file__).resolve().parents[1] / "scripts" / "train_unreal.py"
        spec = importlib.util.spec_from_file_location("train_unreal", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parameter = torch.nn.Parameter(torch.tensor(1.0))
        optimizer = torch.optim.Adam([parameter], lr=0.1)
        old_schedule = WarmupCosineScheduler(optimizer, 0, 1, final_lr=0.001)
        optimizer.step()
        old_schedule.step()
        restored = WarmupCosineScheduler(optimizer, 0, 20, final_lr=0.001)
        restored.load_state_dict(old_schedule.state_dict())
        contract = module.DatasetContract("test", "vqvae", {"model": {"scheduler": {"num_training_steps": 20, "num_warmup_steps": 2}}})
        contract.on_train_start(SimpleNamespace(lr_scheduler_configs=[SimpleNamespace(scheduler=restored)]), None)
        self.assertEqual(restored.last_epoch, 1)
        self.assertEqual(restored.num_training_steps, 20)
        self.assertEqual(restored.num_warmup_steps, 2)
        self.assertAlmostEqual(optimizer.param_groups[0]["lr"], 0.05)
        self.assertEqual(restored.get_last_lr(), [0.05])

    def test_three_models_and_resume(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "train_unreal.py"
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source"
            source.mkdir()
            (source / "manifest.json").write_text(json.dumps({"schema_version": 1, "clips": ["clip.json"]}), encoding="utf-8")
            (source / "clip.json").write_text(json.dumps(fixture()), encoding="utf-8")
            dataset = folder / "data"
            prepare_function()(source, dataset)
            checkpoints = {}
            for kind in ("vqvae", "root", "pose"):
                output = folder / kind
                command = [sys.executable, str(script), "--model", kind, "--dataset", str(dataset), "--output", str(output),
                           "--max_steps", "1", "--batch_size", "1", "--accelerator", "cpu", "--tiny"]
                if kind == "pose":
                    command += ["--vqvae", str(checkpoints["vqvae"])]
                result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                path = output / "checkpoints" / "final.ckpt"
                checkpoint = torch.load(path, weights_only=False, map_location="cpu")
                self.assertEqual(checkpoint["global_step"], 1)
                self.assertEqual(checkpoint["unreal_contract"]["kind"], kind)
                self.assertTrue(all(torch.isfinite(value).all() for value in checkpoint["state_dict"].values() if value.is_floating_point()))
                metrics = next((output / "metrics").rglob("metrics.csv"))
                with metrics.open() as stream:
                    values = [float(value) for row in csv.DictReader(stream) for key, value in row.items() if "loss" in key and value]
                self.assertTrue(values and np.isfinite(values).all())
                checkpoints[kind] = path
            for kind in ("root", "pose"):
                command = [sys.executable, str(script), "--model", kind, "--dataset", str(dataset), "--output", str(folder / kind),
                           "--resume", str(checkpoints[kind]), "--max_steps", "2", "--batch_size", "1", "--accelerator", "cpu"]
                if kind == "pose":
                    command += ["--vqvae", str(checkpoints["vqvae"])]
                result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                checkpoint = torch.load(checkpoints[kind], weights_only=False, map_location="cpu")
                self.assertEqual(checkpoint["global_step"], 2)
                self.assertEqual(checkpoint["lr_schedulers"][0]["num_training_steps"], 2)
            resumed = subprocess.run([sys.executable, str(script), "--model", "vqvae", "--dataset", str(dataset), "--output", str(folder / "vqvae"),
                                      "--resume", str(checkpoints["vqvae"]), "--max_steps", "2", "--batch_size", "1", "--accelerator", "cpu"],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            checkpoint = torch.load(checkpoints["vqvae"], weights_only=False, map_location="cpu")
            self.assertEqual(checkpoint["global_step"], 2)
            self.assertEqual(checkpoint["lr_schedulers"][0]["num_training_steps"], 2)
            changed_codebook = subprocess.run([sys.executable, str(script), "--model", "pose", "--dataset", str(dataset), "--output", str(folder / "pose"),
                                              "--resume", str(checkpoints["pose"]), "--vqvae", str(checkpoints["vqvae"]), "--max_steps", "2", "--accelerator", "cpu"],
                                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertNotEqual(changed_codebook.returncode, 0)
            self.assertIn("VQ-VAE", changed_codebook.stderr)


if __name__ == "__main__":
    unittest.main()
