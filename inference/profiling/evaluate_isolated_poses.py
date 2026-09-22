"""将短姿态的每个源姿态独立保持24帧重建，诊断相邻姿态上下文影响。"""
import json
from pathlib import Path

import numpy as np
import torch

from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_animgraph import UnrealPoseReconstruction, pack_raw_pose
from inference.profiling.evaluate_unreal_streaming import metric, rms


def evaluate():
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    net, rep, contract = load_vqvae('training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt')
    dataset = Path(contract['config']['data']['folder'])
    skeleton = json.loads((dataset/'skeleton.json').read_text(encoding='utf8'))
    clips = json.loads((dataset/'dataset.json').read_text(encoding='utf8'))['clips']
    wrapper = UnrealPoseReconstruction(net, rep, skeleton, 24, 'endpoints').eval().cuda()
    report = {'completed': False, 'scope': 'Offline per-pose diagnostic: each source pose held independently for24 frames, score decoder center frame12. No temporal action, contact or UE validation. Extra anchors repeat identical information.', 'clips': []}
    with torch.inference_mode():
        for clip in clips:
            if clip['split'] != 'test' or clip['source_frames'] >= 24:
                continue
            with np.load(dataset/clip['raw_file']) as raw:
                packed = pack_raw_pose(raw, skeleton)
            predictions = {name: [] for name in ('isolated2', 'isolated3')}
            for pose in packed:
                sample = torch.from_numpy(np.repeat(pose[None], 25, axis=0)[None]).cuda()
                for name, anchors in [('isolated2', [0, 23]), ('isolated3', [0, 12, 23])]:
                    wrapper.endpoint_mask.zero_(); wrapper.endpoint_mask[:, anchors] = True
                    predictions[name].append(wrapper(sample).cpu().numpy()[0, 12, :, :3])
            item = {'asset': clip['asset'], 'source_frames': len(packed), 'variants': {}}
            for name, values in predictions.items():
                item['variants'][name] = metric(rms(np.stack(values)-packed[:, :, :3]))
            report['clips'].append(item)
            print(json.dumps(item), flush=True)
    report['completed'] = True
    output = Path('output/ai_animation_runtime_pose_references/isolated_short.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf8')


if __name__ == '__main__':
    evaluate()
