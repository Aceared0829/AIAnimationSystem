# Modified by the AIAnimationSystem maintainers: added missing and platform-specific dependencies.

from setuptools import setup, find_packages

setup(
    name="motionbricks",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "torch>=2.0",
        "numpy",
        "einops",
        "mujoco>=3.0",
        "scipy",
        "hydra-core",
        "omegaconf",
        "pytorch-lightning",
        "transformers",
        "pynput",
        "keyboard; platform_system == 'Windows'",
        "python-xlib; platform_system == 'Linux'",
        "matplotlib",
        "vector-quantize-pytorch",
        "colorlog",
        "adam-atan2-pytorch",
    ],
)
