"""建立管线专用 SOMA/UEFN IK Rig 与重定向资产，不修改示例自带资产。"""
import json
import os
from pathlib import Path
import unreal

folder = '/Game/MotionPipeline/Retarget'
work = Path(os.environ['MOTION_PIPELINE_WORK_ROOT'])
source = unreal.load_asset('/Game/MotionPipeline/SOMAReference/soma_base_skel_minimal/SkeletalMeshes/SK_OUTPUT')
target = unreal.load_asset('/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin')
if not source or not target:
    raise RuntimeError('缺少源或目标骨骼网格')
chains = [('Spine', 'Spine1', 'Chest', 'spine_01', 'spine_05'), ('Neck', 'Neck1', 'Head', 'neck_01', 'head')]
for suffix, side in [('l', 'Left'), ('r', 'Right')]:
    chains.extend([(f'Clavicle_{suffix}', side+'Shoulder', side+'Shoulder', 'clavicle_'+suffix, 'clavicle_'+suffix),
                   (f'Arm_{suffix}', side+'Arm', side+'Hand', 'upperarm_'+suffix, 'hand_'+suffix),
                   (f'Leg_{suffix}', side+'Leg', side+'Foot', 'thigh_'+suffix, 'foot_'+suffix),
                   (f'Toe_{suffix}', side+'ToeBase', side+'ToeBase', 'ball_'+suffix, 'ball_'+suffix)])
    for finger in ['Index', 'Middle', 'Ring', 'Pinky']:
        chains.append((finger+'_'+suffix, side+'Hand'+finger+'1', side+'Hand'+finger+'4', finger.lower()+'_metacarpal_'+suffix, finger.lower()+'_03_'+suffix))
    chains.append(('Thumb_'+suffix, side+'HandThumb1', side+'HandThumb3', 'thumb_01_'+suffix, 'thumb_03_'+suffix))


def create(name, cls, factory):
    path = folder+'/'+name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        raise RuntimeError('配置已存在，须显式检查后更新：'+path)
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, cls, factory)
    if not asset:
        raise RuntimeError('创建失败：'+path)
    return asset


rigs = []
for label, mesh, pelvis, index in [('SOMA', source, 'Hips', 1), ('UEFN', target, 'pelvis', 3)]:
    rig = create('IK_'+label, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())
    controller = unreal.IKRigController.get_controller(rig)
    if not controller.set_skeletal_mesh(mesh) or not controller.set_retarget_root(pelvis):
        raise RuntimeError('配置 IK Rig 失败：'+label)
    for chain in chains:
        if str(controller.add_retarget_chain(chain[0], chain[index], chain[index+1], 'None')) != chain[0]:
            raise RuntimeError('配置骨骼链失败：'+str(chain))
    rigs.append(rig)
retargeter = create('RTG_SOMA_UEFN', unreal.IKRetargeter, unreal.IKRetargetFactory())
controller = unreal.IKRetargeterController.get_controller(retargeter)
controller.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, rigs[0])
controller.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, rigs[1])
controller.add_default_ops()
for chain in chains:
    if not controller.set_source_chain(chain[0], chain[0]):
        raise RuntimeError('链映射失败：'+chain[0])
controller.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET)
for asset in [*rigs, retargeter]:
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset):
        raise RuntimeError('保存失败：'+asset.get_path_name())
pose = unreal.AnimPoseExtensions.get_reference_pose(source.skeleton)
ref = []
for name in unreal.AnimPoseExtensions.get_bone_names(pose):
    transform = pose.get_bone_pose(name, unreal.AnimPoseSpaces.WORLD)
    p, q = transform.translation, transform.rotation
    ref.append(dict(name=str(name), position=[p.x,p.y,p.z], rotation=[q.x,q.y,q.z,q.w]))
(work/'retarget_setup_report.json').write_text(json.dumps(dict(source=source.get_path_name(),target=target.get_path_name(),retargeter=retargeter.get_path_name(),chains=chains,source_reference=ref,training_ready=False), indent=2), encoding='utf-8')
