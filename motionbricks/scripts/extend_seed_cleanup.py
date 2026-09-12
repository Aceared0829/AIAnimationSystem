"""Compatibility entry; use data/tools/extend_seed_cleanup.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.extend_seed_cleanup", run_name="__main__")
else:
    from data.tools.extend_seed_cleanup import *
