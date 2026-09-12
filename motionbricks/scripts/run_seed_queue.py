"""Compatibility entry; use data/tools/run_seed_queue.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.run_seed_queue", run_name="__main__")
else:
    from data.tools.run_seed_queue import *
