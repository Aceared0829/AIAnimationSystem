"""重新加载演示资产并核实 CMC Pawn、观测器和低矮顶棚。"""

import unreal


def main():
    world = unreal.EditorLoadingAndSavingUtils.load_map("/MotionWeaverCMCPreview/Maps/L_CMCPreview")
    if not world:
        raise RuntimeError("演示地图加载失败")
    mode = world.get_world_settings().get_editor_property("default_game_mode")
    pawn = unreal.get_default_object(mode).get_editor_property("default_pawn_class")
    unreal.log(f"MW_VERIFY game_mode={mode.get_path_name()} pawn={pawn.get_path_name()}")
    if "SandboxCharacter_CMC" not in pawn.get_path_name():
        raise RuntimeError("演示地图没有使用 GASP CMC 角色")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    for name in ("MotionWeaver_CMC_StateAndRootTrace", "CrouchOnly_LowCeiling"):
        matching = [actor for actor in actors if actor.get_actor_label() == name]
        if len(matching) != 1:
            raise RuntimeError(f"预期一个 {name}，实际 {len(matching)} 个")
        unreal.log(f"MW_VERIFY actor={name} class={matching[0].get_class().get_name()} location={matching[0].get_actor_location()}")


main()
