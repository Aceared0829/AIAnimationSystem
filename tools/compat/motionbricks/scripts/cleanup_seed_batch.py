"""Compatibility entry; use data/tools/cleanup_seed_batch.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.cleanup_seed_batch", run_name="__main__")
else:
    from data.tools.cleanup_seed_batch import *
