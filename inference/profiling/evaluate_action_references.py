"""完整已知动作的起手/中间/结束姿态消融；离线全上下文诊断，不是实时历史推理。"""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from inference.runtime.checkpoint import load_vqvae
from inference.export.export_unreal_animgraph import UnrealPoseReconstruction, pack_raw_pose
from inference.profiling.evaluate_pose_references import select_references
from inference.profiling.evaluate_unreal_streaming import localize, positions, metric, rms


def evaluate(checkpoint, output):
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    net, rep, contract = load_vqvae(checkpoint)
    dataset = Path(contract['config']['data']['folder'])
    skeleton = json.loads((dataset/'skeleton.json').read_text(encoding='utf8'))
    clips = json.loads((dataset/'dataset.json').read_text(encoding='utf8'))['clips']
    bones = skeleton['bones']
    parents = [bone['parent'] for bone in bones]
    tips = [i for i,b in enumerate(bones) if b['name'] in ('hand_l','hand_r','foot_l','foot_r')]
    weights = np.ones(len(bones)); weights[tips] = 4
    report = {'completed':False,'scope':'offline full known action, future poses available; no streaming buffer; full clip padded to multiple4; context exceeds training maximum64, not production deployment evidence','clips':[]}
    output = Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    with torch.inference_mode():
        for clip in clips:
            if clip['split']!='test' or clip['labels']['category']!='Traversal': continue
            with np.load(dataset/clip['raw_file']) as raw: packed=pack_raw_pose(raw,skeleton)
            length = len(packed); width = (length+3)//4*4
            sample = torch.from_numpy(np.concatenate([packed,np.repeat(packed[-1:],width+1-length,axis=0)])[None]).cuda()
            wrapper = UnrealPoseReconstruction(net,rep,skeleton,width,'endpoints').eval().cuda()
            reference = localize(packed,parents); reference_positions=positions(reference,parents)
            item={'asset':clip['asset'],'frames':length,'network_frames':width,'variants':{}}
            for name,count,strategy in [('action2',2,'uniform'),('uniform3',3,'uniform'),('shape3',3,'shape'),('uniform4',4,'uniform'),('shape4',4,'shape')]:
                indices=select_references(packed,count,strategy,weights)
                wrapper.endpoint_mask.zero_(); wrapper.endpoint_mask[:,indices]=True
                predicted=wrapper(sample).cpu().numpy()[0,:length]
                error=predicted[...,:3]-reference_positions
                item['variants'][name]={'indices':indices,'seconds':[round(i/rep.fps,3) for i in indices],
                    'joint_rmse_cm':metric(rms(error)),'endpoint_rmse_cm':metric(rms(error[:,tips])),
                    'velocity_error_cm_per_frame':metric(rms(np.diff(error,axis=0))),
                    'acceleration_error_cm_per_frame2':metric(rms(np.diff(error,n=2,axis=0)))}
            report['clips'].append(item)
            print(json.dumps(item),flush=True)
    report['completed']=True
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    evaluate(args.checkpoint,args.output)
