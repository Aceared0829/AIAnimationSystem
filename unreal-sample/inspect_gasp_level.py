"""只读检查 GASP 默认关卡与 CMC 角色，供独立试验关卡复用。"""

import unreal


LEVEL = "/Game/Levels/DefaultLevel"


def main():
    world = unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
    unreal.log(f"MW_INSPECT world={world.get_path_name()}")
    settings = world.get_world_settings()
    mode = settings.get_editor_property("default_game_mode")
    unreal.log(f"MW_INSPECT game_mode={mode.get_path_name() if mode else 'None'}")
    if mode:
        default_pawn = unreal.get_default_object(mode).get_editor_property("default_pawn_class")
        unreal.log(f"MW_INSPECT default_pawn={default_pawn.get_path_name() if default_pawn else 'None'}")
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        class_name = actor.get_class().get_name()
        if any(name in class_name.lower() for name in ("character", "playerstart", "camera", "game")):
            unreal.log(f"MW_INSPECT actor={actor.get_name()} class={class_name} location={actor.get_actor_location()}")
    for path in ("/Game/Blueprints/SandboxCharacter_CMC", "/Game/Blueprints/GM_Sandbox"):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        unreal.log(f"MW_INSPECT asset={path} class={asset.get_class().get_name() if asset else 'MISSING'}")


main()
