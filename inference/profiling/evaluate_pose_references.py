"""固定24帧历史比较稀疏条件：插值残差或骨盆相对姿态形状选帧，不读取未来。"""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_animgraph import UnrealPoseReconstruction, pack_raw_pose
from inference.profiling.evaluate_unreal_streaming import localize, positions, simulate, metric, rms


def select_references(packed, count, strategy, weights):
    """保留首尾；key 按曲线误差、shape 按姿态区别贪心选取，间隔至少3帧。"""
    length = len(packed)
    if strategy == "uniform":
        return np.linspace(0, length-1, count).round().astype(int).tolist()
    selected = [0, length-1]
    shape = packed[:, :, :3] - packed[:, :1, :3]
    while len(selected) < count:
        scores = []
        for index in range(1, length-1):
            if min(abs(index-anchor) for anchor in selected) < 3:
                continue
            if strategy == 'shape':
                score = min(np.average(np.sum((shape[index]-shape[anchor])**2,axis=-1),weights=weights) for anchor in selected)
            else:
                left = max(anchor for anchor in selected if anchor < index)
                right = min(anchor for anchor in selected if anchor > index)
                fraction = (index-left)/(right-left)
                estimate = packed[left, :, :3]*(1-fraction) + packed[right, :, :3]*fraction
                score = np.average(np.sum((packed[index, :, :3]-estimate)**2, axis=-1), weights=weights)
            scores.append((float(score), index))
        if not scores:
            raise ValueError("无法满足参考数量及最小间隔")
        selected.append(max(scores, key=lambda pair: pair[0])[1])
        selected.sort()
    return selected


def evaluate(checkpoint, output, selection="showcase", reference_set="counts"):
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    net, rep, contract = load_vqvae(checkpoint)
    dataset = Path(contract['config']['data']['folder'])
    skeleton = json.loads((dataset/'skeleton.json').read_text(encoding='utf8'))
    clips = json.loads((dataset/'dataset.json').read_text(encoding='utf8'))['clips']
    selected = [clip for clip in clips if clip['split']=='test']
    if selection == 'showcase':
        seen = set()
        showcase = []
        for clip in selected:
            category = clip['labels']['category']
            if category == 'Traversal' or (category in ('Walk','Run','Crouch','Jump','Idle') and category not in seen):
                showcase.append(clip)
                seen.add(category)
        selected = showcase
    bones = skeleton['bones']
    parents = [bone['parent'] for bone in bones]
    endpoints = [i for i,bone in enumerate(bones) if bone['name'] in ('hand_l','hand_r','foot_l','foot_r')]
    weights = np.ones(len(bones))
    weights[endpoints] = 4.0
    wrapper = UnrealPoseReconstruction(net, rep, skeleton, 24, 'endpoints').eval().cuda()
    variants = {'endpoints2':(2,'uniform'), 'uniform3':(3,'uniform'), 'key3':(3,'key'), 'uniform5':(5,'uniform'), 'key5':(5,'key')}
    if reference_set == 'shape':
        variants = {'endpoints2':(2,'uniform'), 'uniform3':(3,'uniform'), 'key3':(3,'key'), 'shape3':(3,'shape'), 'uniform4':(4,'uniform'), 'shape4':(4,'shape')}
    report = {'completed':False, 'scope':'PyTorch CUDA FP32 quality only, same source frames28..length-9, window24 stride4 delay8; no UE performance claim',
              'selection':selection, 'selector':'key: interpolation residual; shape: farthest pelvis-relative pose from selected references; hands/feet weight4; minimum spacing3; history only',
              'clips':[], 'skipped':[]}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        for clip in selected:
            with np.load(dataset/clip['raw_file']) as raw:
                packed = pack_raw_pose(raw, skeleton)
            if len(packed)-8-28 < 10:
                report['skipped'].append(clip['asset'])
                continue
            source = localize(packed, parents)
            windows = {name:{} for name in variants}
            choices = {name:[] for name in variants}
            for end in range(23, len(packed), 4):
                history = packed[end-23:end+1]
                sample = torch.from_numpy(np.concatenate([history, history[-1:]])[None]).cuda()
                for name,(count,strategy) in variants.items():
                    indices = select_references(history, count, strategy, weights)
                    wrapper.endpoint_mask.zero_()
                    wrapper.endpoint_mask[:, indices] = True
                    prediction = wrapper(sample).cpu().numpy()[0]
                    windows[name][end] = localize(prediction, parents)
                    choices[name].append({'window_end':end,'indices':indices})
            outputs = {name:simulate(source,value,8,24) for name,value in windows.items()}
            common = sorted(set(range(28,len(source)-8)).intersection(*(set(value) for value in outputs.values())))
            if len(common)<10 or np.any(np.diff(common)!=1):
                raise ValueError('源区间不连续')
            reference = source[common]
            reference_positions = positions(reference,parents)
            item = {'asset':clip['asset'],'category':clip['labels']['category'],'source_interval':[common[0],common[-1]],
                    'samples':len(common),'variants':{},'selected_references':choices}
            for name,frames in outputs.items():
                pose = np.stack([frames[index] for index in common])
                predicted = positions(pose,parents)
                error = predicted-reference_positions
                angles = 2*np.arccos(np.clip(np.abs(np.sum(pose[...,3:]*reference[...,3:],axis=-1)),0,1))*180/np.pi
                item['variants'][name] = {'joint_rmse_cm':metric(rms(error)), 'endpoint_rmse_cm':metric(rms(error[:,endpoints])),
                    'rotation_rmse_degrees':metric(np.sqrt(np.mean(angles**2,axis=-1))),
                    'velocity_error_cm_per_frame':metric(rms(np.diff(error,axis=0))),
                    'acceleration_error_cm_per_frame2':metric(rms(np.diff(error,n=2,axis=0)))}
            report['clips'].append(item)
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps({'category':item['category'],'asset':item['asset'].split('/')[-1],
                              'rmse':{name:round(value['joint_rmse_cm']['mean'],3) for name,value in item['variants'].items()}}),flush=True)
    report['completed'] = True
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--selection',choices=('showcase','test'),default='showcase')
    parser.add_argument('--reference-set',choices=('counts','shape'),default='counts')
    args = parser.parse_args()
    evaluate(args.checkpoint,args.output,args.selection,args.reference_set)
