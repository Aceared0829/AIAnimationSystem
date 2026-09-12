"""Compatibility entry; use data/tools/recover_partial_seed_batch.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.recover_partial_seed_batch", run_name="__main__")
else:
    from data.tools.recover_partial_seed_batch import *
