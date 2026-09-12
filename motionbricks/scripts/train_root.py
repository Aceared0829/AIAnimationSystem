"""Compatibility entry; use training/pretrain/train_root.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("training.pretrain.train_root", run_name="__main__")
else:
    from training.pretrain.train_root import *
