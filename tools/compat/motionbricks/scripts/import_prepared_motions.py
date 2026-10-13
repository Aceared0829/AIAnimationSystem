"""Compatibility entry; use data/tools/import_prepared_motions.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.import_prepared_motions", run_name="__main__")
else:
    from data.tools.import_prepared_motions import *
