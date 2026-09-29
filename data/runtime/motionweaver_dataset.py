"""Prepared UE body motions paired with independent Actor Root trajectories."""

import numpy as np
import torch

from motionbricks.data.synthetic_dataset import collate_batch
from motionbricks.data.unreal_dataset import UnrealMotionDataset, contained_file, file_sha256, read_json


class MotionWeaverUnrealDataset(UnrealMotionDataset):
    """Keep body token targets and Actor Root conditions as distinct tracks."""

    def __init__(self, folder, actor_root_sidecar):
        super().__init__(folder)
        self.actor_root_sidecar = actor_root_sidecar
        sidecar = read_json(contained_file(actor_root_sidecar, "actor_roots_manifest.json"))
        if sidecar.get("source_dataset_manifest_sha256") != file_sha256(self.folder / "dataset.json"):
            raise ValueError("Actor Root sidecar does not match the dataset manifest")
        if sidecar.get("training_signature") != self.manifest["training_signature"]:
            raise ValueError("Actor Root sidecar skeleton/statistics signature mismatch")
        if sidecar.get("coordinates") != "motion_m_y_up_xyzw" or sidecar.get("fps") != self.manifest["fps"]:
            raise ValueError("Actor Root sidecar coordinate system or FPS mismatch")
        records = sidecar.get("records", [])
        if len(records) != len(self.files):
            raise ValueError("Actor Root sidecar clip count mismatch")
        self.actor_root_files = []
        for index, (record, clip) in enumerate(zip(records, self.manifest["clips"])):
            if (record.get("index") != index or record.get("motion_file") != clip["file"]
                    or record.get("frames") != clip["frames"] or record.get("split") != clip["split"]):
                raise ValueError(f"Actor Root alignment mismatch at clip {index}")
            path = contained_file(actor_root_sidecar, record["file"])
            if file_sha256(path) != record["sha256"]:
                raise ValueError(f"Actor Root sidecar hash mismatch at clip {index}")
            track = np.load(path, mmap_mode="r", allow_pickle=False)
            if track.shape != (clip["frames"], 7) or not np.isfinite(track).all():
                raise ValueError(f"Actor Root sidecar shape or values invalid at clip {index}")
            self.actor_root_files.append(path)

    def __getitem__(self, index):
        item = super().__getitem__(index)
        item["actor_root_track"] = torch.from_numpy(
            np.load(self.actor_root_files[index], allow_pickle=False).copy()
        )
        return item


def collate_motionweaver(batch):
    result = collate_batch(batch)
    tracks = torch.zeros((len(batch), result["motion"].shape[1], 7), dtype=torch.float32)
    for index, item in enumerate(batch):
        track = item["actor_root_track"]
        if len(track) != len(item["motion"]):
            raise ValueError("Actor Root and body motion frame lengths differ")
        tracks[index, :len(track)] = track
    result["actor_root_track"] = tracks
    return result
