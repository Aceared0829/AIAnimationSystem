"""条件生成器的硬参考约束和分区评估选择。"""

import unittest

import numpy as np
import torch

from inference.runtime.conditioned_pose import rotation_6d_to_matrix
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

    def test_inference_rotation_is_orthonormal(self):
        values = np.array([[1, 0, 0, 1, 0, 0], [0, 0, 0, 0, 0, 0]], dtype=np.float32)
        matrices = rotation_6d_to_matrix(values)
        np.testing.assert_allclose(matrices @ matrices.transpose(0, 2, 1),
                                   np.broadcast_to(np.eye(3), (2, 3, 3)), atol=1e-6)
        np.testing.assert_allclose(np.linalg.det(matrices), 1, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
