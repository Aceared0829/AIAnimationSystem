"""用刚性动画夹具执行小网络训练、检查点衔接和续训；不评估生成质量。"""

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import torch

from test_unreal_dataset import fixture, prepare_function


class UnrealTrainingTests(unittest.TestCase):
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
            resumed = subprocess.run([sys.executable, str(script), "--model", "vqvae", "--dataset", str(dataset), "--output", str(folder / "vqvae"),
                                      "--resume", str(checkpoints["vqvae"]), "--max_steps", "2", "--batch_size", "1", "--accelerator", "cpu"],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
            self.assertEqual(torch.load(checkpoints["vqvae"], weights_only=False, map_location="cpu")["global_step"], 2)
            changed_codebook = subprocess.run([sys.executable, str(script), "--model", "pose", "--dataset", str(dataset), "--output", str(folder / "pose"),
                                              "--resume", str(checkpoints["pose"]), "--vqvae", str(checkpoints["vqvae"]), "--max_steps", "2", "--accelerator", "cpu"],
                                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            self.assertNotEqual(changed_codebook.returncode, 0)
            self.assertIn("VQ-VAE", changed_codebook.stderr)


if __name__ == "__main__":
    unittest.main()
