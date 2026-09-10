"""在 UE 中生成瞬态 AnimSequence，写入局部轨道后检查实际求值结果。"""
import json
import math
import os
from pathlib import Path
import unreal

ROOT=Path(os.environ['MOTION_PIPELINE_WORK_ROOT']).resolve()
request=json.loads((ROOT/'ue_roundtrip_input.json').read_text())
skeleton=unreal.load_asset('/Game/Characters/UEFN_Mannequin/Meshes/SK_UEFN_Mannequin')
factory=unreal.AnimSequenceFactory()
factory.target_skeleton=skeleton
reports=[]
for clip in request['clips']:
    try:
        asset=unreal.AssetToolsHelpers.get_asset_tools().create_asset('RT_'+clip['name'],'/Game/BonesSeedValidation',unreal.AnimSequence,factory)
        if not asset:
            raise RuntimeError('无法创建验证动画')
        # 修改结构体视图中的默认压缩采样率，不重设只读的父属性。
        rate = asset.get_editor_property('PlatformTargetFrameRate')
        rate.set_editor_property('Default', unreal.FrameRate(clip['fps'],1))
        if asset.get_editor_property('PlatformTargetFrameRate').get_editor_property('Default').numerator != clip['fps']:
            raise RuntimeError('压缩采样率未应用')
        controller=asset.controller
        controller.open_bracket('BONES-SEED roundtrip',False)
        controller.set_frame_rate(unreal.FrameRate(clip['fps'],1),False)
        controller.set_number_of_frames(unreal.FrameNumber(len(clip['tracks'][0])-1),False)
        for name,keys in zip(request['names'],clip['tracks']):
            if not controller.add_bone_curve(name,False):
                raise RuntimeError('无法添加骨骼 '+name)
            if not controller.set_bone_track_keys(name,[unreal.Vector(*k[:3]) for k in keys],[unreal.Quat(*k[3:]) for k in keys],[unreal.Vector(1,1,1)]*len(keys),False):
                raise RuntimeError('无法写入骨骼 '+name)
        controller.close_bracket(False)
        options=unreal.AnimPoseEvaluationOptions()
        options.evaluation_type=unreal.AnimDataEvalType.RAW
        options.should_retarget=False
        options.extract_root_motion=False
        options.incorporate_root_motion_into_pose=True
        max_pos=0.
        max_angle=0.
        for frame,expected in zip(clip['checks'],clip['expected']):
            pose=unreal.AnimPoseExtensions.get_anim_pose_at_time(asset,frame/clip['fps'],options)
            root=pose.get_bone_pose('root',unreal.AnimPoseSpaces.WORLD)
            for i,(name,ref) in enumerate(zip(request['names'],expected)):
                transform=pose.get_bone_pose(name,unreal.AnimPoseSpaces.WORLD)
                if i:
                    transform=unreal.MathLibrary.make_relative_transform(transform,root)
                p=transform.translation
                q=transform.rotation
                max_pos=max(max_pos,math.sqrt(sum((a-b)**2 for a,b in zip([p.x,p.y,p.z],ref[:3]))))
                dot=abs(sum(a*b for a,b in zip([q.x,q.y,q.z,q.w],ref[3:])))
                max_angle=max(max_angle,math.degrees(2*math.acos(min(1.,dot))))
        reports.append(dict(name=clip['name'],max_position_cm=max_pos,max_rotation_deg=max_angle,engine_roundtrip_pass=max_pos<0.05 and max_angle<0.1))
        # 未保存的试验资产由短生命周期命令进程释放；不强制卸载仍被 Python 引用的包。
    except Exception as exc:
        reports.append(dict(name=clip['name'],error=str(exc),engine_roundtrip_pass=False))
    (ROOT/'ue_roundtrip_report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')

if not reports or not all(r.get('engine_roundtrip_pass') for r in reports):
    raise RuntimeError('UE roundtrip validation failed; see ue_roundtrip_report.json')
