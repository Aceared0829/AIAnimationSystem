"""手选资产参考；比较历史24与已知代理动画前瞻24，不声称未知未来预测。"""
import json
from pathlib import Path
import numpy as np
import torch
from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_animgraph import UnrealPoseReconstruction, pack_raw_pose
from inference.profiling.evaluate_unreal_streaming import localize, positions, simulate, metric, rms


CURATED = {
    'M_Neutral_Traversal_Catch_Hurdle_low_run': [(32,'屈身抬腿'),(52,'高抬腿越障'),(64,'躯干展开')],
    'M_Relaxed_Traversal_Catch_Hurdle_med_stand': [(32,'俯身伸展'),(46,'收腿'),(62,'回正过渡')],
    'M_Neutral_Traversal_Mantle_1_0_run_F_Rfoot': [(14,'前伸姿态'),(22,'收腿上台')],
    'M_Relaxed_Traversal_Vault_1_0_run_F_Lfoot': [(23,'俯身跨步'),(35,'横身收腿'),(42,'躯干回正')],
}


def evaluate():
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    net,rep,contract=load_vqvae('training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt')
    dataset=Path(contract['config']['data']['folder'])
    skeleton=json.loads((dataset/'skeleton.json').read_text(encoding='utf8'))
    clips=json.loads((dataset/'dataset.json').read_text(encoding='utf8'))['clips']
    parents=[b['parent'] for b in skeleton['bones']]
    names={b['name']:i for i,b in enumerate(skeleton['bones'])}
    groups={k:[names[n] for n in ns] for k,ns in {'hands':['hand_l','hand_r'],'feet':['foot_l','foot_r'],'knees':['calf_l','calf_r'],'torso':['pelvis','spine_03','spine_05','head']}.items()}
    wrappers={w:UnrealPoseReconstruction(net,rep,skeleton,w,'endpoints').eval().cuda() for w in (24,48)}
    variants={'history24':(24,False),'curated24':(24,True),'proxy48':(48,False),'curated_proxy48':(48,True)}
    report={'completed':False,'scope':'Four diagnostic test examples; manually curated after source inspection, not held-out generalization. Proxy48 encodes known source animation including24 future frames, NOT sparse-only prediction. Same display interval/history-start/stride4/delay8. No UE agent, motion matching, root-follow or transition generation implementation.',
        'selection':'Asset-specific fixed frames; source skeleton visually inspected. Pose descriptions do not assert obstacle contact.', 'clips':[]}
    output=Path('output/ai_animation_runtime_pose_references/proxy_curated.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    archive={};manifest={}
    with torch.inference_mode():
        for clip in clips:
            name=clip['asset'].split('/')[-1].split('.')[0]
            if name not in CURATED or clip['split']!='test':continue
            with np.load(dataset/clip['raw_file']) as raw:packed=pack_raw_pose(raw,skeleton)
            anchors=[0]+[f for f,_ in CURATED[name]]+[len(packed)-1]
            assert all(0<=f<len(packed) for f in anchors) and anchors==sorted(set(anchors))
            manifest[clip['asset']]={'fps':30,'frames':anchors,'middle_poses':[{'frame':f,'description':s} for f,s in CURATED[name]]}
            source=localize(packed,parents);windows={v:{} for v in variants};reference_counts={v:[] for v in variants}
            for end in range(23,len(packed),4):
                start=end-23
                for variant,(width,curated) in variants.items():
                    indices=np.arange(start,start+width).clip(max=len(packed)-1)
                    history=packed[indices]
                    sample=torch.from_numpy(np.concatenate([history,history[-1:]])[None]).cuda()
                    last=min(width-1,len(packed)-1-start)
                    refs=sorted(set([0,last]+([f-start for f in anchors if start<=f<=start+last] if curated else [])))
                    wrapper=wrappers[width];wrapper.endpoint_mask.zero_();wrapper.endpoint_mask[:,refs]=True
                    prediction=wrapper(sample).cpu().numpy()[0,:24]
                    windows[variant][end]=localize(prediction,parents)
                    reference_counts[variant].append({'end':end,'frames':[start+i for i in refs]})
            common=list(range(28,len(source)-8));reference=positions(source[common],parents)
            key=str(len(report['clips']));archive[key+'_source']=reference
            item={'asset':clip['asset'],'category':'Traversal','source_interval':[common[0],common[-1]],'references':manifest[clip['asset']],'variants':{},'window_references':reference_counts}
            for variant,windows_by_end in windows.items():
                streamed=simulate(source,windows_by_end,8,24)
                predicted=positions(np.stack([streamed[i] for i in common]),parents)
                error=predicted-reference;per_frame=rms(error)
                measurements={'joint_rmse_cm':metric(per_frame),'acceleration_error_cm_per_frame2':metric(rms(np.diff(error,n=2,axis=0))),
                    'frames_over_10cm':int((per_frame>10).sum()),'worst_frame':common[int(per_frame.argmax())],
                    'regions':{g:metric(rms(error[:,ids])) for g,ids in groups.items()},'reference_errors':[]}
                for anchor in anchors:
                    entry={'frame':anchor,'scored':anchor in common}
                    if anchor in common:
                        i=anchor-common[0];near=error[max(0,i-2):i+3]
                        entry.update(joint_cm=float(per_frame[i]),regions={g:metric(rms(error[i:i+1,ids])) for g,ids in groups.items()},nearby_regions={g:metric(rms(near[:,ids])) for g,ids in groups.items()})
                    measurements['reference_errors'].append(entry)
                item['variants'][variant]=measurements;archive[key+'_'+variant]=predicted
            report['clips'].append(item)
            print(json.dumps({'asset':name,'refs':anchors,'errors':{v:round(m['joint_rmse_cm']['mean'],3) for v,m in item['variants'].items()}}),flush=True)
    report['completed']=True
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    output.with_name('proxy_curated_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    np.savez_compressed(output.with_suffix('.npz'),**archive)


if __name__=='__main__':evaluate()
