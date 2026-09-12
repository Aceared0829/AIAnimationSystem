"""Compatibility entry; use data/tools/run_overnight_seed_pipeline.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.run_overnight_seed_pipeline", run_name="__main__")
else:
    from data.tools.run_overnight_seed_pipeline import *
