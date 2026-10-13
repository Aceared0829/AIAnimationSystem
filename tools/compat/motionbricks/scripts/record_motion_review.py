"""Compatibility entry; use data/tools/record_motion_review.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.record_motion_review", run_name="__main__")
else:
    from data.tools.record_motion_review import *
