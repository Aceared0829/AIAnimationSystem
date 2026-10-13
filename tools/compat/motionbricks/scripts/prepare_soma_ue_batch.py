"""Compatibility entry; use data/tools/prepare_soma_ue_batch.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.prepare_soma_ue_batch", run_name="__main__")
else:
    from data.tools.prepare_soma_ue_batch import *
