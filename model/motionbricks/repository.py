"""Locations of repository resources, independent of the process working directory."""
import os
from pathlib import Path


def repository_root():
    root = Path(os.environ.get('AIANIMATION_ROOT', Path(__file__).resolve().parents[2])).resolve()
    if not (root / 'model').is_dir() or not (root / 'training').is_dir():
        raise RuntimeError('Repository resources are unavailable; set AIANIMATION_ROOT to the AIAnimationSystem checkout.')
    return root


def base_weights():
    return repository_root() / 'model-weight/base/motionbricks'


def unreal_scripts():
    return repository_root() / 'unreal-script/python'
