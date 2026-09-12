"""Compatibility entry; use data/tools/run_ue_pipeline_check.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.run_ue_pipeline_check", run_name="__main__")
else:
    from data.tools.run_ue_pipeline_check import *
