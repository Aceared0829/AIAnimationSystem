"""导航帧缓存初始化与待机重规划的回归检查。"""
import unittest
from types import SimpleNamespace

import torch

from inference.demo.full_agent import full_navigation_agent


class NavigationRegenerationTests(unittest.TestCase):
    def test_initial_and_existing_modes(self):
        for previous, current, expected in ((None, 0, True), (0, 0, False)):
            with self.subTest(previous=previous, current=current):
                agent = full_navigation_agent.__new__(full_navigation_agent)
                torch.nn.Module.__init__(agent)
                agent._clip_holder = SimpleNamespace(CLIPS={'idle': {}, 'walk': {}})
                agent.frames = {} if previous is None else {'mode': torch.tensor([previous])}
                self.assertEqual(agent._should_regenerate({'mode': torch.tensor([current])}), expected)


if __name__ == '__main__':
    unittest.main()
