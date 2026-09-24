"""条件生成器的硬参考约束和分区评估选择。"""

import unittest

import torch

from training.evaluation.evaluate_conditioned_pose import center_indices
from training.pretrain.train_conditioned_pose import ReferenceGuidedPose, losses


class ConditionedPoseTrainingTests(unittest.TestCase):
    def test_hard_references_are_exact_and_unmasked_frames_train(self):
        model = ReferenceGuidedPose(bones=2, width=32)
        history = torch.randn(2, 24, 25)
        root = torch.randn(2, 24, 7)
        reference = torch.zeros(2, 24, 18)
        reference[:, 12] = torch.randn(2, 18)
        mask = torch.zeros(2, 24, 1)
        mask[:, 12] = 1
        prediction = model(history, root, reference, mask)
        torch.testing.assert_close(prediction[:, 12], reference[:, 12])
        loss = losses(prediction, torch.randn_like(prediction), mask, torch.ones(2, 3))[0]
        loss.backward()
        self.assertTrue(torch.isfinite(loss))
        self.assertIsNotNone(model.output[-1].weight.grad)

    def test_center_window_selection_matches_clip_order(self):
        rows = [{"clip_index": 7, "start": 0}, {"clip_index": 3, "start": 0},
                {"clip_index": 7, "start": 4}, {"clip_index": 3, "start": 4},
                {"clip_index": 7, "start": 8}]
        self.assertEqual(center_indices(rows), [3, 2])


if __name__ == "__main__":
    unittest.main()
