from hydra.utils import instantiate
from omegaconf import DictConfig, ListConfig


def load_motion_rep(conf: DictConfig | ListConfig):
    if not isinstance(conf, DictConfig):
        raise ValueError("Motion configuration must be a mapping")
    skeleton = instantiate(conf.skeleton)
    motion_rep = instantiate(conf.motion_rep, fps=conf.fps, skeleton=skeleton)
    return motion_rep
