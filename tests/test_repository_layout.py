"""Exercise installed imports, old contracts and real export after folder migration."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch

from test_unreal_dataset import pose_only_fixture, prepare_function

ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayoutTests(unittest.TestCase):
    def test_inference_imports_without_training_or_plotting_from_other_cwd(self):
        code = '''
import importlib.abc
import sys
class BlockTraining(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pytorch_lightning', 'matplotlib', 'mujoco', 'training'}:
            raise AssertionError('Unexpected inference dependency: ' + fullname)
sys.meta_path.insert(0, BlockTraining())
from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_inference import load_package
from motionbricks.motion_backbone.inference.motion_inference import motion_inference
from motionbricks.vqvae.neural_modules.vqvae import VQVAE
from motionbricks.repository import base_weights
assert (base_weights() / 'motionbricks_vqvae/version_1/hparams.yaml').is_file()
'''
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run([sys.executable, '-c', code], cwd=cwd, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_checkpoint_class_alias(self):
        from motionbricks.data.unreal_quality import UnrealQualityVQVAE as old
        from motionbricks.training.unreal_quality import UnrealQualityVQVAE as new
        self.assertIs(old, new)

    def test_pose_only_train_export_reload_is_numerically_equal(self):
        self._train_export_roundtrip('cpu')

    @unittest.skipUnless(torch.cuda.is_available(), 'CUDA is unavailable')
    def test_gpu_training_and_exported_package_profiling(self):
        self._train_export_roundtrip('gpu')

    def _train_export_roundtrip(self, accelerator):
        from inference.runtime.checkpoint import load_vqvae
        from inference.export.export_unreal_inference import export, load_package
        from motionbricks.data.unreal_dataset import UnrealMotionDataset
        from motionbricks.helper.data_training_util import extract_feature_from_motion_rep

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'source'
            source.mkdir()
            (source / 'clip.json').write_text(json.dumps(pose_only_fixture()))
            (source / 'manifest.json').write_text(json.dumps({'schema_version': 2, 'training_contract': 'pose_only_root_authoritative', 'clips': ['clip.json']}))
            dataset_folder = folder / 'dataset'
            prepare_function()(source, dataset_folder)
            result = subprocess.run([sys.executable, str(ROOT / 'training/pretrain/train_unreal.py'),
                                     '--model', 'vqvae', '--dataset', str(dataset_folder), '--output', str(folder / 'run'),
                                     '--max_steps', '1', '--batch_size', '1', '--accelerator', accelerator, '--tiny'],
                                    cwd=folder, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            checkpoint = folder / 'run/checkpoints/final.ckpt'
            net, rep, contract = load_vqvae(checkpoint)
            self.assertEqual(contract['training_contract'], 'pose_only_root_authoritative')
            dataset = UnrealMotionDataset(dataset_folder)
            motion = dataset[0]['motion'][:64][None]
            local = rep.dual_rep.global_to_local(motion, is_normalized=True, to_normalize=True, lengths=torch.tensor([64]))
            condition = extract_feature_from_motion_rep(local, net.motion_rep, net.decoder_external_cond_feature_mode)
            with torch.no_grad():
                expected = net(local, target_cond=None, has_target_cond=None, external_cond=condition)['recon_state']
            report = export(checkpoint, folder / 'package')
            self.assertTrue(report['state_bitwise_equal'])
            restored, _ = load_package(folder / 'package')
            with torch.no_grad():
                actual = restored(local, target_cond=None, has_target_cond=None, external_cond=condition)['recon_state']
            torch.testing.assert_close(expected, actual, rtol=0, atol=0)
            export(checkpoint, folder / 'decoder', decoder_only=True)
            decoder, _ = load_package(folder / 'decoder')
            self.assertFalse(hasattr(decoder, 'encoder'))
            codes = torch.zeros((1, local.shape[1] // 4), dtype=torch.long)
            with torch.no_grad():
                expected_decoder = net.forward_decoder(codes, target_cond=None, external_cond=condition)
                actual_decoder = decoder.forward_decoder(codes, target_cond=None, external_cond=condition)
            torch.testing.assert_close(expected_decoder, actual_decoder, rtol=0, atol=0)
            if accelerator == 'gpu':
                import numpy as np
                motion_path = folder / 'motion.npy'
                np.save(motion_path, motion[0].numpy())
                result = subprocess.run([sys.executable, str(ROOT / 'inference/profiling/profile_unreal_inference.py'),
                                         '--packages', str(folder / 'package'), str(folder / 'decoder'),
                                         '--motion', str(motion_path), '--output', str(folder / 'profile.json')],
                                        cwd=folder, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                profile = json.loads((folder / 'profile.json').read_text(encoding='utf-8'))
                self.assertEqual(len(profile['results']), 2)
                for entry in profile['results']:
                    self.assertTrue(np.isfinite(entry['median_ms']) and entry['median_ms'] > 0)


if __name__ == '__main__':
    unittest.main()
