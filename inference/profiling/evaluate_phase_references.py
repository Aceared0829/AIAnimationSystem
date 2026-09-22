"""已知跑酷资产的阶段候选与条件遵守审计；阶段语义须人工/接触标注确认。"""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_animgraph import UnrealPoseReconstruction, pack_raw_pose
from inference.profiling.evaluate_unreal_streaming import localize, positions, simulate, metric, rms


def phase_candidates(packed, names):
    """仅提出可审查的运动学候选，不把手脚高度当成接触真值。"""
    n = len(packed)
    if n == 0:
        raise ValueError('源动画不能为空')
    if n < 9:
        return [{'phase': 'start', 'frame': 0, 'basis': 'asset boundary', 'confirmed': True}] + (
            [{'phase': 'end', 'frame': n-1, 'basis': 'asset boundary', 'confirmed': True}] if n > 1 else [])
    p = packed[:, :, :3]-packed[:, :1, :3]
    knees = p[:, [names['calf_l'], names['calf_r']], 2].max(axis=1)
    # 抬膝幅度不足时不强行制造越障阶段。
    middle = int(np.argmax(knees[3:n-3]))+3
    result = [{'phase': 'start', 'frame': 0, 'basis': 'asset boundary', 'confirmed': True}]
    if np.ptp(knees) > 10 and 5 <= middle < n-5:
        hands = p[:, [names['hand_l'], names['hand_r']]]
        reach = np.linalg.norm(hands[:, :, :2], axis=-1).max(axis=1)
        support = int(np.argmax(reach[2:middle-1]))+2
        result.append({'phase': 'support_candidate', 'frame': support, 'basis': 'maximum horizontal hand reach before knee peak', 'confirmed': False})
        result.append({'phase': 'clearance_candidate', 'frame': middle, 'basis': 'maximum pelvis-relative knee height', 'confirmed': False})
        speed = np.linalg.norm(np.diff(hands, axis=0, prepend=hands[:1]), axis=-1).max(axis=1)
        stop = min(n-3, middle+max(5,n//4))
        release = int(np.argmax(speed[middle+2:stop]))+middle+2
        result.append({'phase': 'release_candidate', 'frame': release, 'basis': 'maximum hand motion after knee peak; not verified contact release', 'confirmed': False})
        # 稳定低脚位置只提供落地候选，没有场景地面信息。
        feet = p[:, [names['foot_l'],names['foot_r']]]
        foot_speed = np.linalg.norm(np.diff(feet,axis=0,prepend=feet[:1]),axis=-1).mean(axis=1)
        if release+3 < n-3:
            ids = np.arange(release+3,n-2)
            score = feet[ids,:,2].min(axis=1)+2*foot_speed[ids]
            landing = int(ids[np.argmin(score)])
            result.append({'phase': 'landing_candidate', 'frame': landing, 'basis': 'low and slow feet after release candidate; not verified ground contact', 'confirmed': False})
    result.append({'phase': 'end', 'frame': n-1, 'basis': 'asset boundary', 'confirmed': True})
    return result


def region_metrics(error, groups):
    return {name: metric(rms(error[:, indices])) for name, indices in groups.items()}


def evaluate(output, override=None):
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    net,rep,contract=load_vqvae('training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt')
    dataset=Path(contract['config']['data']['folder'])
    skeleton=json.loads((dataset/'skeleton.json').read_text(encoding='utf8'))
    clips=json.loads((dataset/'dataset.json').read_text(encoding='utf8'))['clips']
    names={b['name']:i for i,b in enumerate(skeleton['bones'])}
    parents=[b['parent'] for b in skeleton['bones']]
    groups={label:[names[x] for x in joints] for label,joints in {
        'hands':['hand_l','hand_r'],'feet':['foot_l','foot_r'],
        'knees':['calf_l','calf_r'],'torso':['pelvis','spine_03','spine_05','head']}.items()}
    groups['all']=list(range(len(parents)))
    wrapper=UnrealPoseReconstruction(net,rep,skeleton,24,'endpoints').eval().cuda()
    overrides=json.loads(Path(override).read_text(encoding='utf8')) if override else {}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    report={'completed':False,'scope':'Offline known-asset phase annotation candidates using full source clip. Decoder receives only history24, stride4 delay8. Selection is not an online phase detector. Start/end excluded from steady-state stream scoring; direct decoder audit includes boundaries. No verified contacts or gameplay validation.',
        'target_feature_mode':net.decoder_target_cond_feature_mode,'clips':[],'skipped':[]}
    manifest={};archive={}
    with torch.inference_mode():
        for clip in clips:
            if clip['labels']['category']!='Traversal' or clip['split']=='train':continue
            with np.load(dataset/clip['raw_file']) as raw:packed=pack_raw_pose(raw,skeleton)
            if len(packed) < 46:
                report['skipped'].append({'asset':clip['asset'],'reason':'Fewer than10 steady-state frames for history24/stride4/delay8'})
                continue
            phases=overrides.get(clip['asset'],phase_candidates(packed,names))
            for phase in phases:
                if type(phase['frame']) is not int or not 0<=phase['frame']<len(packed):raise ValueError('阶段帧越界')
            manifest[clip['asset']]=phases
            anchors=sorted(set(p['frame'] for p in phases))
            source=localize(packed,parents)
            windows={v:{} for v in ('endpoints2','phase','phase_band')}
            item={'asset':clip['asset'],'split':clip['split'],'phases':phases,'reference_count':len(anchors),'variants':{},'decoder_reference_audit':[]}
            # 额外末窗口只用于边界审计；simulate 仍按原步长读取窗口。
            for end in sorted(set(range(23,len(source),4)) | {len(source)-1}):
                start=end-23;history=packed[start:end+1]
                sample=torch.from_numpy(np.concatenate([history,history[-1:]])[None]).cuda()
                for variant in windows:
                    extra=[] if variant=='endpoints2' else anchors
                    if variant=='phase_band':extra=[a+d for a in anchors for d in (-1,0,1)]
                    ids=sorted(set([0,23]+[a-start for a in extra if start<=a<=end]))
                    wrapper.endpoint_mask.zero_();wrapper.endpoint_mask[:,ids]=True
                    prediction=wrapper(sample).cpu().numpy()[0]
                    windows[variant][end]=localize(prediction,parents)
                    for anchor in anchors:
                        if not start<=anchor<=end:continue
                        offsets=np.arange(max(start,anchor-2),min(end,anchor+2)+1)-start
                        at=anchor-start
                        item['decoder_reference_audit'].append({'variant':variant,'window_end':end,'frame':anchor,'conditioned':at in ids,
                            'can_affect_stream':(end-23)%4==0 and end<anchor+8,'anchor':region_metrics((prediction[at:at+1,:,:3]-history[at:at+1,:,:3]),groups),
                            'nearby':region_metrics(prediction[offsets,:,:3]-history[offsets,:,:3],groups)})
            common=list(range(28,len(source)-8));reference=positions(source[common],parents)
            key=str(len(report['clips']));archive[key+'_source']=reference
            for variant,win in windows.items():
                stream=simulate(source,win,8,24)
                prediction=positions(np.stack([stream[i] for i in common]),parents)
                error=prediction-reference;frame_errors=rms(error)
                result={'regions':region_metrics(error,groups),'acceleration_error':metric(rms(np.diff(error,n=2,axis=0))),
                    'worst_frame':common[int(frame_errors.argmax())],'frames_over_10cm':int((frame_errors>10).sum()),'phase_errors':[]}
                for phase in phases:
                    frame=phase['frame'];entry={**phase,'scored':frame in common}
                    if frame in common:
                        i=frame-28;ids=np.arange(max(0,i-2),min(len(common),i+3))
                        entry.update(anchor=region_metrics(error[i:i+1],groups),nearby=region_metrics(error[ids],groups))
                    result['phase_errors'].append(entry)
                item['variants'][variant]=result;archive[key+'_'+variant]=prediction
            report['clips'].append(item)
            output.write_text(json.dumps(report,indent=2),encoding='utf8')
            print(json.dumps({'asset':clip['asset'].split('/')[-1],'count':len(anchors),'error':{v:round(r['regions']['all']['mean'],3) for v,r in item['variants'].items()}}),flush=True)
    report['completed']=True
    output.write_text(json.dumps(report,indent=2),encoding='utf8')
    output.with_name('phase_reference_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    np.savez_compressed(output.with_suffix('.npz'),**archive)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='output/ai_animation_runtime_pose_references/phases.json')
    parser.add_argument('--manifest')
    args=parser.parse_args();evaluate(args.output,args.manifest)
