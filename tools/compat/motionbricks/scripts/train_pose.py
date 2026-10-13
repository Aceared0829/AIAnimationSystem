"""Compatibility entry; use training/pretrain/train_pose.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("training.pretrain.train_pose", run_name="__main__")
else:
    from training.pretrain.train_pose import *
