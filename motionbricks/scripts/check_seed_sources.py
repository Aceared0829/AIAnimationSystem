"""Compatibility entry; use data/tools/check_seed_sources.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.check_seed_sources", run_name="__main__")
else:
    from data.tools.check_seed_sources import *
