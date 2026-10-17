"""数值运动、可逆 Root 代理、多高度接触候选与未知掩码。"""

import unittest
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from data.runtime.motion_features import extract_features
from data.runtime.motion_processing import contact_candidates, process_motion
from data.runtime.native_motion import SampledMotion, SourceInfo
from data.runtime.skeleton_contract import load_skeleton_contract


class MotionFeatureTests(unittest.TestCase):
    def test_parameterized_features(self):
        for case in ("translation", "rotation", "inverted_singleton", "contact_levels"):
            with self.subTest(case=case):
                skeleton, contract = load_skeleton_contract(Path(__file__).parents[1] / "data/skeletons/soma_uniform_v1.json")
                count = 1 if case == "inverted_singleton" else 21
                times = np.arange(count) / 10
                motion = SampledMotion(skeleton, times, np.tile(skeleton.rest_positions, (count, 1, 1)),
                    np.tile(skeleton.rest_rotations, (count, 1, 1)), np.tile(skeleton.rest_scales, (count, 1, 1)),
                    np.ones((len(skeleton.names), 3), dtype=bool), SourceInfo("hidden_source_label", {}, "fixture"),
                    float(times[-1]), 10., 0)
                if case == "translation":
                    motion.positions[:, 0, 2] += times
                elif case == "rotation":
                    turn = Rotation.from_euler("y", np.linspace(0, 90, count)[:, None], degrees=True)
                    motion.rotations[:, 0] = (turn * Rotation.from_quat(motion.rotations[:, 0])).as_quat()
                elif case == "inverted_singleton":
                    motion.rotations[:, 0] = (Rotation.from_euler("z", 180, degrees=True)
                        * Rotation.from_quat(motion.rotations[:, 0])).as_quat()
                before = motion.positions.copy()
                features = extract_features(motion, contract["roles"])
                arrays, summary = process_motion(motion, contract["roles"])
                np.testing.assert_array_equal(before, motion.positions)
                self.assertLess(summary["recomposition_max_abs_error_m"], 1e-10)
                np.testing.assert_array_equal(arrays["timestamps"], times)
                self.assertTrue((arrays["root_proxy"][:, 1] == 0).all())
                if case == "translation":
                    np.testing.assert_allclose(features["role_positions"][-1, 0] - features["role_positions"][0, 0], [0, 0, 2])
                    self.assertGreater(np.median(features["body_forward_right_speed_m_s"][:, 0]), .99)
                elif case == "rotation":
                    self.assertAlmostEqual(float(features["heading_step_deg"].sum()), 90, delta=.01)
                elif case == "inverted_singleton":
                    self.assertFalse(features["heading_valid"].any())
                    self.assertTrue((arrays["contact_states"] == -1).all())
                    self.assertFalse(arrays["contact_known_mask"].any())
                else:
                    # 两个稳定高度之间移动；悬空静止的手不被升级为接触。
                    names = ["lf", "lt", "rf", "rt", "lh", "rh"]
                    roles = dict(zip(("left_foot", "left_toe", "right_foot", "right_toe", "left_hand", "right_hand"), names))
                    world = np.zeros((61, 6, 3))
                    world[:, :2, 1] = np.clip((np.arange(61) - 20) / 20, 0, 1)[:, None] * .5
                    world[:, [0, 2], 1] += .06
                    world[:, 4:, 1] = 1.5
                    contacts, evidence = contact_candidates(world, np.arange(61) / 30, names, roles)
                    np.testing.assert_allclose(evidence["left_foot"]["stable_height_levels_m"], [0, .5])
                    self.assertEqual(contacts["contact_states"][10, 0], 1)
                    self.assertEqual(contacts["contact_states"][30, 0], 0)
                    self.assertEqual(contacts["contact_states"][50, 0], 1)
                    self.assertTrue((contacts["contact_states"][:, 2:] == -1).all())
                    self.assertFalse(contacts["contact_known_mask"][:, 2:].any())



if __name__ == "__main__":
    unittest.main()
