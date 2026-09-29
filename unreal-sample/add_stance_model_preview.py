"""只在现有独立 CMC 演示地图增加一个 B1 模型 Actor，不改动 GASP 原地图。"""

import unreal


MAP_PATH = "/MotionWeaverCMCPreview/Maps/L_CMCPreview"
ACTOR_LABEL = "MotionWeaver_B1_CMC_ModelPose"


def main():
    world = unreal.EditorLoadingAndSavingUtils.load_map(MAP_PATH)
    if not world:
        raise RuntimeError(f"无法加载演示地图：{MAP_PATH}")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    existing = [actor for actor in actors.get_all_level_actors() if actor.get_actor_label() == ACTOR_LABEL]
    if len(existing) > 1:
        raise RuntimeError(f"重复模型 Actor：{len(existing)}")
    if existing:
        unreal.log(f"MW_MODEL_ACTOR_EXISTS {existing[0].get_path_name()}")
        return
    actor_class = unreal.load_class(None, "/Script/MotionWeaverCMCPreview.MotionWeaverStancePreviewActor")
    if not actor_class:
        raise RuntimeError("模型预览 C++ 类未加载")
    actor = actors.spawn_actor_from_class(actor_class, unreal.Vector(-800.0, 0.0, 90.0))
    if not actor:
        raise RuntimeError("创建模型预览 Actor 失败")
    actor.set_actor_label(ACTOR_LABEL)
    if not unreal.EditorLevelLibrary.save_current_level():
        raise RuntimeError("保存模型演示地图失败")
    unreal.log(f"MW_MODEL_ACTOR_ADDED {actor.get_path_name()}")


main()
