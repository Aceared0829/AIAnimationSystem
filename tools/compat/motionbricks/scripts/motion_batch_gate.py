"""Compatibility entry; use data/tools/motion_batch_gate.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.motion_batch_gate", run_name="__main__")
else:
    from data.tools.motion_batch_gate import *
