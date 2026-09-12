"""Compatibility entry; use data/tools/validate_seed_training.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.validate_seed_training", run_name="__main__")
else:
    from data.tools.validate_seed_training import *
