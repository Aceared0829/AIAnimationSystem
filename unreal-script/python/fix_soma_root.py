"""修复管线自有重定向配置：从目标骨盆生成地面平移，不引入骨盆倾斜到 Root。"""
import unreal

asset = unreal.load_asset('/Game/MotionPipeline/Retarget/RTG_SOMA_UEFN')
controller = unreal.IKRetargeterController.get_controller(asset)
found = False
for index in range(controller.get_num_retarget_ops()):
    op = controller.get_op_controller(index)
    if isinstance(op, unreal.IKRetargetRootMotionController):
        unreal.log('Root op enabled before: '+str(controller.get_retarget_op_enabled(index)))
        controller.set_retarget_op_enabled(index, True)
        op.set_source_root_bone('Root')
        op.set_target_root_bone('root')
        op.set_target_pelvis_bone('pelvis')
        settings = op.get_settings()
        settings.root_motion_source = unreal.RootMotionSource.GENERATE_FROM_TARGET_PELVIS
        settings.root_height_source = unreal.RootMotionHeightSource.SNAP_TO_GROUND
        settings.rotate_with_pelvis = False
        settings.maintain_offset_from_pelvis = False
        op.set_settings(settings)
        unreal.log('Root motion source after: '+str(op.get_settings().root_motion_source))
        found = True
if not found or not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
    raise RuntimeError('根运动配置更新失败')
