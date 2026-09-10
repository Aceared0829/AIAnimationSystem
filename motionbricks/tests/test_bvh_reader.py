"""解析器的通道顺序、父子 FK 与截断拒绝测试。"""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from motionbricks.data.bvh_reader import read_bvh

class BvhReaderTests(unittest.TestCase):
    def parse(self, values):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'test.bvh'
            path.write_text('''HIERARCHY
ROOT Root {
OFFSET 0 0 0
CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation
JOINT Hips {
OFFSET 1 0 0
CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation
End Site { OFFSET 1 0 0 }
}
}
MOTION
Frames: 1
Frame Time: 0.01
''' + values)
            return read_bvh(path)

    def test_root_rotation_applies_to_child_offset_and_translation(self):
        p,r = self.parse('10 20 30 90 0 0 2 0 0 0 0 0').forward()
        np.testing.assert_allclose(p[0,1],[10,23,30],atol=1e-10)
        np.testing.assert_allclose(r[0,1] @ [1,0,0],[0,1,0],atol=1e-10)

    def test_truncated_channel_data_rejected(self):
        with self.assertRaises(ValueError):
            self.parse('10 20 30 90 0 0 2 0 0 0 0')

    def test_nonfinite_values_rejected(self):
        with self.assertRaises(ValueError):
            self.parse('nan 20 30 90 0 0 2 0 0 0 0 0')

if __name__=='__main__':
    unittest.main()
