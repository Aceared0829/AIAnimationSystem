"""Compatibility entry; use data/tools/audit_ue_batch.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("data.tools.audit_ue_batch", run_name="__main__")
else:
    from data.tools.audit_ue_batch import *
