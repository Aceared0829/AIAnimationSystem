"""Compatibility entry; use training/evaluation/diagnose_unreal_capacity.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("training.evaluation.diagnose_unreal_capacity", run_name="__main__")
else:
    from training.evaluation.diagnose_unreal_capacity import *
