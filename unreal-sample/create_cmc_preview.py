"""在 GASP 的独立插件内容中创建 CMC 单机观测地图，不覆盖源地图。"""

import unreal


SOURCE_MAP = "/Game/Levels/DefaultLevel"
TARGET_MAP = "/MotionWeaverCMCPreview/Maps/L_CMCPreview"
SOURCE_MODE = "/Game/Blueprints/GM_Sandbox"
TARGET_MODE = "/MotionWeaverCMCPreview/Blueprints/BP_GM_CMCPreview"
CMC_CHARACTER = "/Game/Blueprints/SandboxCharacter_CMC"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    assets = unreal.EditorAssetLibrary
    require(not assets.does_asset_exist(TARGET_MAP), f"目标地图已存在，拒绝覆盖：{TARGET_MAP}")
    require(not assets.does_asset_exist(TARGET_MODE), f"目标 GameMode 已存在，拒绝覆盖：{TARGET_MODE}")
    require(assets.does_asset_exist(SOURCE_MAP), f"源地图不存在：{SOURCE_MAP}")
    require(assets.does_asset_exist(SOURCE_MODE), f"源 GameMode 不存在：{SOURCE_MODE}")

    cloned_mode = assets.duplicate_asset(SOURCE_MODE, TARGET_MODE)
    require(cloned_mode, "复制演示 GameMode 失败")
    mode_class = assets.load_blueprint_class(TARGET_MODE)
    cmc_class = assets.load_blueprint_class(CMC_CHARACTER)
    require(mode_class and cmc_class, "演示 GameMode 或 GASP CMC 角色类不可加载")
    unreal.get_default_object(mode_class).set_editor_property("default_pawn_class", cmc_class)
    require(assets.save_loaded_asset(cloned_mode), "保存演示 GameMode 失败")

    cloned_map = assets.duplicate_asset(SOURCE_MAP, TARGET_MAP)
    require(cloned_map, "复制演示地图失败")
    world = unreal.EditorLoadingAndSavingUtils.load_map(TARGET_MAP)
    require(world, "演示地图无法加载")
    world.get_world_settings().set_editor_property("default_game_mode", mode_class)

    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    trace_class = unreal.load_class(None, "/Script/MotionWeaverCMCPreview.MotionWeaverCMCTraceActor")
    require(trace_class, "观测 Actor 的 C++ 类未加载")
    trace = actors.spawn_actor_from_class(trace_class, unreal.Vector(-800.0, 0.0, 90.0))
    require(trace, "无法在演示地图生成观测 Actor")
    trace.set_actor_label("MotionWeaver_CMC_StateAndRootTrace")

    roof = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(-500.0, 0.0, 145.0))
    require(roof, "无法在演示地图生成低矮顶棚")
    roof.set_actor_label("CrouchOnly_LowCeiling")
    roof.set_actor_scale3d(unreal.Vector(3.0, 3.0, 0.2))
    cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")
    require(cube, "引擎基础立方体不可加载")
    roof.get_component_by_class(unreal.StaticMeshComponent).set_static_mesh(cube)

    require(unreal.EditorLevelLibrary.save_current_level(), "保存演示地图失败")
    unreal.log(f"MW_PREVIEW_CREATED map={TARGET_MAP} game_mode={TARGET_MODE} pawn={CMC_CHARACTER}")
    unreal.log(f"MW_PREVIEW_CREATED roof={roof.get_actor_location()} trace={trace.get_actor_location()}")


main()
