"""将 SOMA 源轨道写入 UE，并通过原生 IK Retargeter 生成目标动画。"""
import json
import os
from pathlib import Path
import unreal

work = Path(os.environ['MOTION_PIPELINE_WORK_ROOT']).resolve()
request = json.loads((work/'soma_batch_request.json').read_text(encoding='utf-8'))
if not 1 <= len(request['clips']) <= 8:
    raise ValueError('试验批量必须为 1..8')
batch_id = request['batch_id']
if not batch_id.startswith('B_') or not batch_id[2:].isalnum():
    raise ValueError('非法批次标识')
folder = '/Game/MotionPipeline/'+batch_id
source = unreal.load_asset('/Game/MotionPipeline/SOMAReference/soma_base_skel_minimal/SkeletalMeshes/SK_OUTPUT')
target = unreal.load_asset('/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin')
retargeter = unreal.load_asset('/Game/MotionPipeline/Retarget/RTG_SOMA_UEFN')
if not all([source,target,retargeter]):
    raise RuntimeError('缺少重定向资产')
factory = unreal.AnimSequenceFactory()
factory.target_skeleton = source.skeleton
assets = []
for clip in request['clips']:
    # 末尾字母阻止 UE 资产重命名把哈希末尾长数字当序号解析并截断。
    name = 'SRC_'+clip['sha256'][:24]+'x'
    if unreal.EditorAssetLibrary.does_asset_exist(folder+'/Source/'+name):
        if os.environ.get('MOTION_PIPELINE_REUSE_SOURCE') == '1':
            existing = unreal.load_asset(folder+'/Source/'+name)
            if existing.get_skeleton() != source.skeleton:
                raise RuntimeError('已有源资产绑定错误')
            assets.append(unreal.EditorAssetLibrary.find_asset_data(existing.get_path_name()))
            continue
        raise RuntimeError('试验资产已存在，拒绝隐式覆盖')
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name,folder+'/Source',unreal.AnimSequence,factory)
    if not asset:
        raise RuntimeError('无法创建源动画：'+name)
    rate = asset.get_editor_property('PlatformTargetFrameRate')
    rate.set_editor_property('Default',unreal.FrameRate(clip['fps'],1))
    controller = asset.controller
    controller.open_bracket('Import SOMA source tracks',False)
    controller.set_frame_rate(unreal.FrameRate(clip['fps'],1),False)
    controller.set_number_of_frames(unreal.FrameNumber(len(clip['tracks'][0])-1),False)
    for bone,keys in zip(request['names'],clip['tracks']):
        if not controller.add_bone_curve(bone,False):
            raise RuntimeError('源骨骼轨道创建失败：'+bone)
        if not controller.set_bone_track_keys(bone,[unreal.Vector(*k[:3]) for k in keys],[unreal.Quat(*k[3:]) for k in keys],[unreal.Vector(1,1,1)]*len(keys),False):
            raise RuntimeError('源轨道写入失败：'+bone)
    controller.close_bracket(False)
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset):
        raise RuntimeError('源试验资产保存失败')
    assets.append(unreal.EditorAssetLibrary.find_asset_data(asset.get_path_name()))
inputs = unreal.IKRetargetBatchOperationInputs()
inputs.assets_to_retarget = assets
inputs.source_mesh = source
inputs.target_mesh = target
inputs.ik_retarget_asset = retargeter
revision = os.environ.get('MOTION_PIPELINE_TARGET_REVISION','Target')
if not revision.isalnum():
    raise ValueError('非法目标版本')
inputs.target_path = folder+'/'+revision
inputs.search = 'SRC_'
inputs.replace = 'UEFN_'
inputs.include_referenced_assets = False
inputs.overwrite_existing_files = False
results = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
report = []
for data in results:
    asset = data.get_asset()
    if asset.get_skeleton() != target.skeleton:
        raise RuntimeError('目标骨骼绑定错误')
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset):
        raise RuntimeError('目标资产保存失败')
    report.append(dict(asset=asset.get_path_name(),skeleton=asset.get_skeleton().get_path_name(),training_ready=False))
(work/'soma_batch_retarget_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if len(report) != len(request['clips']):
    raise RuntimeError('UE 重定向输出数量不匹配')
