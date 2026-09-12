import unittest
import torch
from motionbricks.training.unreal_quality import PoseAwareBatchSampler


class PoseAwareTests(unittest.TestCase):
    def test_short_samples_are_not_batched_with_long_sequences(self):
        items = [{"source_frames": n, "labels": {"category": c}} for n, c in [(8, "Poses"), (12, "Poses"), (28, "Jump"), (60, "Ragdoll"), (130, "Walk")]]
        torch.manual_seed(42)
        sampler = PoseAwareBatchSampler(items * 100, 4)
        def bucket(n):
            return next((limit for limit in [16, 32, 64] if n <= limit), 128)
        seen = set()
        for batch in sampler:
            self.assertEqual(len(batch), 4)
            self.assertEqual(len({bucket((items * 100)[i]["source_frames"]) for i in batch}), 1)
            seen.update(bucket((items * 100)[i]["source_frames"]) for i in batch)
        self.assertEqual(seen, {16, 32, 64, 128})

    def test_sampling_is_reproducible_and_has_bounded_epoch_length(self):
        items = [{"source_frames": 12, "labels": {"category": "Poses"}} for _ in range(9)]
        sampler = PoseAwareBatchSampler(items, 4)
        torch.manual_seed(5)
        first = list(sampler)
        torch.manual_seed(5)
        self.assertEqual(first, list(sampler))
        self.assertEqual(len(first), 3)
