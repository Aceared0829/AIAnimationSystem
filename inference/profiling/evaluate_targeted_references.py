"""按首次重建的具体问题姿态补参考；短片仅计真实帧，长片维持历史窗口。"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_animgraph import UnrealPoseReconstruction, pack_raw_pose
from inference.profiling.evaluate_pose_references import select_references
from inference.profiling.evaluate_unreal_streaming import localize, positions, simulate, metric, rms


def problem_frame(source, prediction, selected, groups):
    # 骨盆相对误差用于找姿态问题，避免整个人平移主导选帧。
    error = (prediction[:, :, :3] - prediction[:, :1, :3]) - (source[:, :, :3] - source[:, :1, :3])
    scores = np.stack([rms(error[:, indices]) for indices in groups.values()], axis=1)
    valid = [i for i in range(len(source)) if min(abs(i-j) for j in selected) >= 3]
    if not valid:
        return None
    frame = max(valid, key=lambda i: float(scores[i].max()))
    region = list(groups)[int(scores[frame].argmax())]
    return frame, region, float(scores[frame].max())


def evaluate(checkpoint, output, selection='test'):
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    net, rep, contract = load_vqvae(checkpoint)
    dataset = Path(contract['config']['data']['folder'])
    skeleton = json.loads((dataset/'skeleton.json').read_text(encoding='utf8'))
    clips = json.loads((dataset/'dataset.json').read_text(encoding='utf8'))['clips']
    bones = skeleton['bones']
    parents = [b['parent'] for b in bones]
    lookup = {b['name']: i for i, b in enumerate(bones)}
    groups = {name: [lookup[b] for b in names] for name, names in {
        'left_arm': ['upperarm_l', 'lowerarm_l', 'hand_l'],
        'right_arm': ['upperarm_r', 'lowerarm_r', 'hand_r'],
        'left_leg': ['thigh_l', 'calf_l', 'foot_l', 'ball_l'],
        'right_leg': ['thigh_r', 'calf_r', 'foot_r', 'ball_r'],
        'torso_head': ['spine_03', 'spine_05', 'neck_01', 'head'],
    }.items()}
    tips = [lookup[b] for b in ('hand_l', 'hand_r', 'foot_l', 'foot_r')]
    weights = np.ones(len(bones)); weights[tips] = 4
    wrapper = UnrealPoseReconstruction(net, rep, skeleton, 24, 'endpoints').eval().cuda()
    variants = ['endpoints2', 'shape4', 'targeted3', 'targeted4', 'dense_diagnostic']
    report = {'completed': False, 'checkpoint': str(checkpoint),
        'scope': 'Known-source reconstruction only. Long clips: history24/stride4/delay8, shared steady-state frames. Short clips: offline known clip, end-held to24, score original frames only. No UE or performance validation.',
        'selector': 'Iteratively select largest pelvis-relative body-region reconstruction error, at least3 frames apart. Re-decode with full pose reference; no output overwrite. Dense is a diagnostic control, not deployment.',
        'clips': [], 'skipped': []}
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    archive = {}
    with torch.inference_mode():
        for clip in clips:
            split = 'validation' if selection == 'validation-traversal' else 'test'
            categories = ('Traversal',) if selection == 'validation-traversal' else ('AimOffset', 'Poses', 'Ragdoll', 'Interactions', 'Traversal', 'Slide')
            if clip['split'] != split or clip['labels']['category'] not in categories:
                continue
            with np.load(dataset/clip['raw_file']) as raw:
                packed = pack_raw_pose(raw, skeleton)
            length = len(packed)
            if length < 10:
                report["skipped"].append({"asset":clip["asset"],"reason":"Fewer than10 real frames for four references with minimum spacing3"})
                continue
            short = length < 46
            if 24 < length < 46:
                report['skipped'].append({'asset': clip['asset'], 'reason': 'Too long for short24, fewer than10 steady-state frames for streaming'})
                continue
            source = localize(packed, parents)
            windows = {name: {} for name in variants}
            choices = []
            ends = [length-1] if short else range(23, length, 4)
            for end in ends:
                history = packed if short else packed[end-23:end+1]
                # 长度24以上但不足稳态评测区间的片段不混入短片实验。
                if len(history) > 24:
                    break
                n = len(history)
                padded = np.concatenate([history, np.repeat(history[-1:], 25-n, axis=0)])
                sample = torch.from_numpy(padded[None]).cuda()
                def decode(indices):
                    wrapper.endpoint_mask.zero_(); wrapper.endpoint_mask[:, indices] = True
                    return wrapper(sample).cpu().numpy()[0]
                selected = [0, n-1]
                predictions = {'endpoints2': decode(selected)}
                details = {'end': end, 'added': []}
                for name in ('targeted3', 'targeted4'):
                    previous = predictions['endpoints2' if name == 'targeted3' else 'targeted3']
                    problem = problem_frame(history, previous[:n], selected, groups)
                    if problem is not None:
                        frame, region, error = problem
                        selected.append(frame)
                        details['added'].append({'frame': end-n+1+frame, 'region': region, 'error_cm': error})
                    predictions[name] = decode(selected)
                predictions['shape4'] = decode(select_references(history, 4, 'shape', weights))
                predictions['dense_diagnostic'] = decode(list(range(n)))
                choices.append(details)
                for name, prediction in predictions.items():
                    windows[name][end] = localize(prediction[:n] if short else prediction, parents)
            if not choices:
                continue
            if short:
                common = list(range(length))
                outputs = {name: windows[name][length-1] for name in variants}
            else:
                streamed = {name: simulate(source, value, 8, 24) for name, value in windows.items()}
                common = sorted(set(range(28, length-8)).intersection(*(set(v) for v in streamed.values())))
                outputs = {name: np.stack([streamed[name][i] for i in common]) for name in variants}
            reference = positions(source[common], parents)
            item = {'asset': clip['asset'], 'split': split, 'category': clip['labels']['category'], 'mode': 'short_offline' if short else 'streaming',
                'source_frames': length, 'source_interval': [common[0], common[-1]], 'samples': len(common),
                'source_motion_rms_cm': float(rms(np.diff(packed[:, :, :3], axis=0)).mean()),
                'variants': {}, 'choices': choices}
            key = str(len(report['clips']))
            archive[key+'_source'] = reference
            for name, pose in outputs.items():
                predicted = positions(pose, parents)
                error = predicted-reference
                item['variants'][name] = {'joint_rmse_cm': metric(rms(error)), 'endpoint_rmse_cm': metric(rms(error[:, tips])),
                    'velocity_error_cm_per_frame': metric(rms(np.diff(error, axis=0))),
                    'acceleration_error_cm_per_frame2': metric(rms(np.diff(error, n=2, axis=0))),
                    'regions_cm': {region: metric(rms(error[:, indices])) for region, indices in groups.items()}}
                archive[key+'_'+name] = predicted
            report['clips'].append(item)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps({'asset': clip['asset'].split('/')[-1], 'mode': item['mode'],
                'errors': {name: round(v['joint_rmse_cm']['mean'], 3) for name, v in item['variants'].items()}}), flush=True)
    report['completed'] = True
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    np.savez_compressed(output.with_suffix('.npz'), **archive)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--selection', choices=('test', 'validation-traversal'), default='test')
    args = parser.parse_args()
    evaluate(args.checkpoint, args.output, args.selection)
