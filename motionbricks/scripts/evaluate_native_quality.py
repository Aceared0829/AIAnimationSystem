"""Compatibility entry; use training/evaluation/evaluate_native_quality.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("training.evaluation.evaluate_native_quality", run_name="__main__")
else:
    from training.evaluation.evaluate_native_quality import *
