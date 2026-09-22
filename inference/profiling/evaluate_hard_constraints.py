"""用户指定关键帧：软推理、直接覆盖、平滑硬约束三方离线对照。"""
import json
from pathlib import Path
import numpy as np
import inference.profiling.pose_reference_lab as runtime
from inference.profiling.evaluate_unreal_streaming import positions,rms


def evaluate():
    lab=runtime.Lab();captured={}
    project=runtime.constrain_poses
    def capture(soft,reference,frames,anchors):
        captured.update(soft=soft,reference=reference,frames=frames,anchors=anchors)
        return project(soft,reference,frames,anchors)
    runtime.constrain_poses=capture
    try:result=lab.infer((32,34,44,52,56,59),'proxy',True)
    finally:runtime.constrain_poses=project
    soft=captured['soft'];target=captured['reference'];frames=captured['frames'];anchors=captured['anchors']
    naive=soft.copy();ids=[frames.index(f) for f in anchors if f in frames];naive[ids]=target[ids]
    hard=project(soft,target,frames,anchors)
    source_positions=positions(target,lab.parents)
    report={'scope':'Known selected poses; post-fusion offline experiment, no weight change, no UE runtime proof. Zero anchor error is enforced by construction.', 'references':list(anchors),'variants':{}}
    for name,pose in [('soft',soft),('snap_only',naive),('smooth_hard',hard)]:
        predicted=positions(pose,lab.parents);error=predicted-source_positions
        lengths=np.linalg.norm(pose[:,1:,:3],axis=-1);source_lengths=np.linalg.norm(target[:,1:,:3],axis=-1)
        near=sorted(set(i+d for i in ids for d in (-2,-1,0,1,2) if 1<=i+d<len(frames)-1))
        accel=rms(np.diff(error,n=2,axis=0))
        report['variants'][name]={'mean_cm':float(rms(error).mean()),'acceleration_error':float(accel.mean()),
            'anchor_neighbor_acceleration_error':float(accel[np.array(near)-1].mean()),
            'max_local_bone_length_difference_cm':float(np.abs(lengths-source_lengths).max())}
    output=Path('output/ai_animation_runtime_pose_references/hard_constraint_comparison.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':evaluate()
