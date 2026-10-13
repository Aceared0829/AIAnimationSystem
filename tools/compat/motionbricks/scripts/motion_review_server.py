"""Compatibility entry; use data/tools/motion_review_server.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.motion_review_server", run_name="__main__")
else:
    from data.tools.motion_review_server import *
