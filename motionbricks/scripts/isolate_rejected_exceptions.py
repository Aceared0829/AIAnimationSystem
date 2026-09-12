"""Compatibility entry; use data/tools/isolate_rejected_exceptions.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.isolate_rejected_exceptions", run_name="__main__")
else:
    from data.tools.isolate_rejected_exceptions import *
