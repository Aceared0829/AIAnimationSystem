"""针对用户圈出的36/52/54帧，强制给予参考并审计解码前后误差。"""
import json
from pathlib import Path
import numpy as np
import torch
from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_animgraph import UnrealPoseReconstruction, pack_raw_pose
from inference.profiling.evaluate_unreal_streaming import localize, positions, simulate, metric, rms


def audit():
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    net, rep, contract = load_vqvae('training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt')
    dataset = Path(contract['config']['data']['folder'])
    skeleton = json.loads((dataset/'skeleton.json').read_text(encoding='utf8'))
    clips = json.loads((dataset/'dataset.json').read_text(encoding='utf8'))['clips']
    clip = next(c for c in clips if 'Neutral_Traversal_Catch_Hurdle_low_run.' in c['asset'])
    with np.load(dataset/clip['raw_file']) as raw:
        packed = pack_raw_pose(raw, skeleton)
    parents = [b['parent'] for b in skeleton['bones']]
    source = localize(packed, parents)
    wrapper = UnrealPoseReconstruction(net, rep, skeleton, 24, 'endpoints').eval().cuda()
    anchors = {'endpoints2': [], 'marked_frames': [36,52,54],
        'marked_bands': list(range(33,40))+list(range(50,58)), 'dense': list(range(len(source)))}
    windows = {name: {} for name in anchors}
    report = {'completed': False, 'asset': clip['asset'], 'scope': 'User-selected source frame anchors, single-clip diagnostic, not generalization. Only known history supplied. Same window24 stride4 delay8; no pose overwrite.', 'windows': [], 'variants': {}}
    with torch.inference_mode():
        for end in range(23, len(source), 4):
            start = end-23
            history = packed[start:end+1]
            sample = torch.from_numpy(np.concatenate([history, history[-1:]])[None]).cuda()
            for name, selected in anchors.items():
                indices = sorted(set([0,23]+[f-start for f in selected if start<=f<=end]))
                wrapper.endpoint_mask.zero_(); wrapper.endpoint_mask[:,indices] = True
                predicted = wrapper(sample).cpu().numpy()[0]
                windows[name][end] = localize(predicted, parents)
                # 给出尚能影响播放的窗口，便于区分解码偏差与融合问题。
                for frame in (36,52,54):
                    if start<=frame<=end and end<frame+8:
                        offset = frame-start
                        error = predicted[offset,:,:3]-packed[frame,:,:3]
                        report['windows'].append({'variant': name,'window_end': end,'frame': frame,
                            'is_reference': offset in indices,'references': [i+start for i in indices],
                            'decoder_rmse_cm': float(rms(error))})
    arrays = {}
    for name, values in windows.items():
        streamed = simulate(source, values, 8, 24)
        common = list(range(28,len(source)-8))
        prediction = positions(np.stack([streamed[i] for i in common]),parents)
        reference = positions(source[common],parents)
        error = prediction-reference
        report['variants'][name] = {'joint_rmse_cm': metric(rms(error)),
            'marked_frame_rmse_cm': {str(f): float(rms(error[f-28])) for f in (36,52,54)},
            'acceleration_error_cm_per_frame2': metric(rms(np.diff(error,n=2,axis=0)))}
        arrays[name] = prediction
    arrays['source'] = reference
    report['completed'] = True
    output = Path('output/ai_animation_runtime_pose_references/marked_frame_audit.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf8')
    np.savez_compressed(output.with_suffix('.npz'), **arrays)
    print(json.dumps(report['variants'],indent=2))


if __name__ == '__main__':
    audit()
