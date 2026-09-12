"""Compatibility entry; use training/evaluation/evaluate_unreal_vqvae.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("training.evaluation.evaluate_unreal_vqvae", run_name="__main__")
else:
    from training.evaluation.evaluate_unreal_vqvae import *
