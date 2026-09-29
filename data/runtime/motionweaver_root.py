"""Convert an independent Actor Root track into a Pose Token trajectory.

Input transforms use the prepared UE Motion coordinate system: metres,
right-handed Y up, and xyzw quaternions. The first Actor transform defines the
local coordinate frame for each prediction window. ``corrective_yaw`` is the
same rotation applied to the body representation by ``change_first_heading``.
"""

import torch


def actor_track_to_condition(actor_root, corrective_yaw=0.0):
    """Return [B,T,4] Actor-local XZ metres and heading cos/sin.

    The result is invariant to a common world translation and yaw rotation of
    the entire Actor track. The corrective yaw then aligns it with the Pose
    Token body's canonicalized heading for this training/inference window.
    """
    if actor_root.ndim != 3 or actor_root.shape[-1] != 7:
        raise ValueError("Actor Root must have shape [batch, frames, 7]")
    if actor_root.shape[1] < 1:
        raise ValueError("Actor Root window is empty")
    if not torch.isfinite(actor_root).all():
        raise ValueError("Actor Root contains non-finite values")
    corrective_yaw = torch.as_tensor(corrective_yaw, device=actor_root.device, dtype=actor_root.dtype)
    if corrective_yaw.ndim == 0:
        corrective_yaw = corrective_yaw.expand(actor_root.shape[0])
    if corrective_yaw.shape != (actor_root.shape[0],):
        raise ValueError("Corrective yaw must have one value per Actor Root window")

    x, y, z, w = actor_root[..., 3:].unbind(dim=-1)
    forward_x = 2 * (x * z + y * w)
    forward_z = 1 - 2 * (x.square() + y.square())
    yaw = torch.atan2(forward_x, forward_z)
    angle = corrective_yaw - yaw[:, 0]
    cosine, sine = torch.cos(angle)[:, None], torch.sin(angle)[:, None]
    displacement = actor_root[..., :3] - actor_root[:, :1, :3]
    horizontal_x = cosine * displacement[..., 0] + sine * displacement[..., 2]
    horizontal_z = -sine * displacement[..., 0] + cosine * displacement[..., 2]
    relative_yaw = yaw - yaw[:, :1] + corrective_yaw[:, None]
    return torch.stack((horizontal_x, horizontal_z, torch.cos(relative_yaw),
                        torch.sin(relative_yaw)), dim=-1)
