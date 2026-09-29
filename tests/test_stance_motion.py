"""站蹲 v2 索引的前置历史补齐、真值边界及标注绑定回归。"""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from data.runtime.conditioned_motion import build_index, sha256
from data.runtime.stance_motion import build_stance_index, early_window_starts, load_stance_window
from test_conditioned_motion_contract import prepared_fixture
from training.pretrain.train_conditioned_pose import ReferenceGuidedPose
from training.pretrain.train_stance_pilot import StanceGuidedPose


class StanceMotionTests(unittest.TestCase):
    def test_zero_stance_embedding_preserves_parent_prediction(self):
        torch.manual_seed(7)
        parent = ReferenceGuidedPose(bones=2, width=32).eval()
        conditioned = StanceGuidedPose(bones=2, width=32).eval()
        missing, unexpected = conditioned.load_state_dict(parent.state_dict(), strict=False)
        self.assertEqual(missing, ["goal_stance.weight"])
        self.assertFalse(unexpected)
        history = torch.randn(1, 24, 25)
        root = torch.randn(1, 24, 7)
        reference = torch.zeros(1, 24, 18)
        mask = torch.zeros(1, 24, 1)
        expected = parent(history, root, reference, mask)
        actual = conditioned(history, root, reference, mask, torch.ones(1, 24, dtype=torch.long))
        torch.testing.assert_close(actual, expected)

    def test_early_history_keeps_transition_in_real_future(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared = prepared_fixture(root, with_short=False)
            base_folder = root / "base"
            base = build_index(prepared, base_folder)
            clip = base["clips"][0]
            annotation = {"schema_version": 1, "base_contract_sha256": sha256(base_folder / "contract.json"),
                          "clips": [{"clip_index": 0, "asset": clip["asset"], "raw_sha256": clip["raw_sha256"],
                                     "from_stance": "stand", "to_stance": "crouch",
                                     "transition_start": 5, "transition_end": 15,
                                     "status": "provisional", "evidence": "测试标注"}]}
            annotations_file = root / "annotations.json"
            annotations_file.write_text(json.dumps(annotation), encoding="utf-8")
            output = root / "stance"
            contract = build_stance_index(base_folder, annotations_file, output)
            self.assertGreater(contract["future_transition_window_split_counts"]["train"], 0)
            rows = [json.loads(line) for line in (output / "windows.jsonl").read_text().splitlines()]
            row = next(item for item in rows if item["start"] == -23)
            sample = load_stance_window(output, row)
            self.assertEqual(sample["input"]["history_valid_mask"].tolist(), [False] * 23 + [True])
            self.assertEqual(sample["target"]["observed_stance"].tolist()[4:15], [2] * 11)
            self.assertEqual(sample["input"]["goal_stance_proxy"].tolist(), [1] * 24)
            self.assertEqual(sample["target"]["future_pose"].shape, (24, base["bone_count"], 3))
            self.assertNotIn("accepted_stance", sample["input"])
            self.assertNotIn("can_uncrouch", sample["input"])
            self.assertTrue(np.isfinite(sample["input"]["future_root_plan_local"]).all())

    def test_bad_hash_and_illegal_future_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared = prepared_fixture(root, with_short=False)
            base_folder = root / "base"
            base = build_index(prepared, base_folder)
            clip = base["clips"][0]
            annotation = {"schema_version": 1, "base_contract_sha256": "wrong",
                          "clips": [{"clip_index": 0, "asset": clip["asset"], "raw_sha256": clip["raw_sha256"],
                                     "from_stance": "stand", "to_stance": "crouch",
                                     "transition_start": 5, "transition_end": 15,
                                     "status": "provisional", "evidence": "测试标注"}]}
            annotations_file = root / "annotations.json"
            annotations_file.write_text(json.dumps(annotation), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "哈希不匹配"):
                build_stance_index(base_folder, annotations_file, root / "rejected")
            self.assertFalse((root / "rejected").exists())
            self.assertEqual(early_window_starts(23), [])
            self.assertEqual(early_window_starts(24), [])
            self.assertEqual(early_window_starts(25), [-23])


if __name__ == "__main__":
    unittest.main()
