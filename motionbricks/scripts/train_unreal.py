"""Compatibility entry; use training/pretrain/train_unreal.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("training.pretrain.train_unreal", run_name="__main__")
else:
    from training.pretrain.train_unreal import *
