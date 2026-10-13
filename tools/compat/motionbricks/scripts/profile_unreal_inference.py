"""Compatibility entry; use inference/profiling/profile_unreal_inference.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("inference.profiling.profile_unreal_inference", run_name="__main__")
else:
    from inference.profiling.profile_unreal_inference import *
