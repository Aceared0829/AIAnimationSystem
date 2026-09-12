"""Compatibility entry; use inference/cli/interactive_demo_g1.py."""
import runpy

if __name__ == "__main__":
    runpy.run_module("inference.cli.interactive_demo_g1", run_name="__main__")
else:
    from inference.cli.interactive_demo_g1 import *
