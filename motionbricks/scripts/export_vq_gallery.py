"""Compatibility entry; use training/evaluation/export_vq_gallery.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("training.evaluation.export_vq_gallery", run_name="__main__")
else:
    from training.evaluation.export_vq_gallery import *
