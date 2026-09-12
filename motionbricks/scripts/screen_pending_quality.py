"""Compatibility entry; use data/tools/screen_pending_quality.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.screen_pending_quality", run_name="__main__")
else:
    from data.tools.screen_pending_quality import *
