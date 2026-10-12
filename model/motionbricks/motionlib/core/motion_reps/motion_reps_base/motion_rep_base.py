
import numpy as np
import torch

from motionbricks.motionlib.core.skeletons import SkeletonBase
from motionbricks.motionlib.core.utils.stats import Stats


class MotionRepBase(torch.nn.Module):
    """Base class for a motion representation."""

    skeleton: SkeletonBase
    stats: Stats | None
    indices: dict[str, np.ndarray]
    root_mode: str

    def __init__(
        self,
        fps: float,
        skeleton: SkeletonBase,
        name: str,
        stats: Stats | None = None,
    ):
        super().__init__()
        self.stats = stats
        # native resolution of the motion
        self.fps = fps
        # skeleton holds joint names and other info like root and feet indices
        #      if need to do FK, also holds parents and neutral pose
        self.skeleton = skeleton

        # name of the motion rep
        self.name = name

        # number of joints in the skeleton
        self.num_joints = self.nbjoints = skeleton.nbjoints

    def normalize(self, motion: torch.Tensor, index=None) -> torch.Tensor:
        """Normalize a feature vector or a index of it.

        Args:
            motion (torch.Tensor): [..., D] the motion to normalize
            index (Optional[index]) the index to crop the motion
        """
        if self.stats is None:
            raise ValueError("Motion statistics are required for normalization")
        return self.stats.normalize(motion, index=index)

    def unnormalize(self, motion: torch.Tensor, index=None) -> torch.Tensor:
        """Unnormalize a normalized motion. Only one of root_only, nonroot_only, and contacts_only
        should be true.

        Args:
            motion (torch.Tensor): [..., D] the motion to unnormalize
            index (Optional[index]) the index to crop the motion
        """
        if self.stats is None:
            raise ValueError("Motion statistics are required for normalization")
        return self.stats.unnormalize(motion, index=index)
