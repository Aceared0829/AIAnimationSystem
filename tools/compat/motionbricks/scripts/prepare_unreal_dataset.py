"""Compatibility entry; use data/tools/prepare_unreal_dataset.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.prepare_unreal_dataset", run_name="__main__")
else:
    from data.tools.prepare_unreal_dataset import *
