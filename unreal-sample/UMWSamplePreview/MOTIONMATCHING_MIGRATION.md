# Motion Matching 迁入项目模块

2026-10-03，使用本机 UE 5.8.3 将 `MotionMatchingInCpp` 的 Gameplay 源码与 Content 迁入 `UMWSamplePreview`。

## 最终目录与依赖

| 原位置或标识 | 当前归属 |
| --- | --- |
| `Plugins/MotionMatchingInCpp/Source/MotionMatchingInCpp/CommonGameplay/` | `Source/UMWSamplePreview/CommonGameplay/`，34 个源文件 |
| `Plugins/MotionMatchingInCpp/Content/` | 项目 `Content/`，保留原有相对目录和 2992 个文件 |
| `/MotionMatchingInCpp/...` | `/Game/...` |
| `/Script/MotionMatchingInCpp` | `/Script/UMWSamplePreview` |
| `MOTIONMATCHINGINCPP_API` | `UMWSAMPLEPREVIEW_API` |

原插件目录、描述文件、模块注册和模块 Build.cs 已移除。Gameplay 代码编入已有的项目游戏模块，不额外建立模块。`MotionWeaver` 插件继续保留在 `Plugins/MotionWeaver`，与其 `unreal-script/MotionWeaver` 镜像的检查通过。

移除了项目原先新增的 `Public/Gameplay/3C`、`Private/Gameplay/3C` 及其空壳 `MotionWeaverCharacter`、`MotionWeaverPlayerController`。如果旧 Blueprint 仍引用这些类型，项目配置会将其重定向到原有 `PlayerCharacter` 和 `AnimPlayerController`。

`UMWSamplePreview.Build.cs` 承接原插件依赖，`UMWSamplePreview.uproject` 显式启用对应引擎插件及 GameplayAbilities。`RewindDebuggerVLog` 仅加入 Editor 构建；Foley AnimNotify 的 `NotifyColor`、`bShouldFireInEditor` 初始化以 `WITH_EDITORONLY_DATA` 保护，保持编辑器行为并允许 Game 构建。

默认地图改为 `/Game/Levels/DefaultLevel`。原插件的历史反射重定向并入项目 `DefaultEngine.ini`，同时保留旧模块路径与当前模块路径下的历史名称兼容。DeviceProfiles、NetworkPrediction 配置迁入项目 Config；补齐源码与资产已经使用、原项目缺少注册的 14 个 Gameplay Tag，保持原有 Tag 名称。

迁入的外部源码保留原有版权标记与来源边界。原插件描述文件标注作者为 Acceered；调整目录不会改变这些代码和动画资产的授权。

## 迁移与验证证据

操作前备份了插件 Source、Content、Config、描述文件以及项目原有 Source、Config、uproject。移动前核对备份，移动后核对目标：全部 2992 个 Content 文件的 SHA-256 相同。之后通过 UE 原生 ResavePackages 和 Blueprint 编译保存更新包引用，没有直接编辑 uasset/umap 二进制。

| 验证项 | 结果 |
| --- | --- |
| Editor Win64 Development | 编译成功 |
| Game Win64 Development | 编译成功，未进行打包或 Cook |
| Rider 项目数据生成 | 成功 |
| Content 文件 | 2992，缺失 0 |
| Asset Registry | 迁移前后均为 2994 条记录，加载失败 0 |
| Blueprint、AnimBlueprint、ControlRig、Widget、Editor Utility | 95 个编译及保存成功，失败 0 |
| Registry 依赖 | 无旧 `/MotionMatchingInCpp/` 或 `/Script/MotionMatchingInCpp` 依赖 |
| 默认关卡 Actor | 迁移前后均为 115 个，类和位置一致（仅规范化路径） |
| GameMode、Pawn、Controller、输入资产、Mesh、AnimBP、CMC 参数及原生组件 | 迁移前后配置一致（仅规范化路径） |
| PIE | 移动、蹲下、站起实测通过；角色与动画实例有效，骨骼数量均为 88 |
| 初始角色位置与相机位置 | 迁移前后完全一致 |

默认链路仍为 `DefaultLevel → GM_Sandbox → SandboxCharacter_CMC / PC_Sandbox → ABP_PlayerCharacter`，现在这些资产全部位于 `/Game`。Gameplay 逻辑与角色参数未重写；源码正文除路径/API 宏转换外，仅增加上述 Editor 专用字段的构建保护。

本机证据位于仓库 `.build/mmcpp-migration/`：`content-manifest.json`、`comparison.json`、`before-assets.json`、`after-assets.json`、`blueprint-validation.json`、构建和 UE 日志，以及迁移前后的 idle/walk/crouch/stand 截图。截图采样时刻不同，不作为逐帧动画或像素相等的证明。原始备份位于同目录的 `backup/`。

本次检查覆盖默认单机演示与所有资产的加载、蓝图编译，没有覆盖联网、每个 Retarget 角色、所有 Traversal 动作或推理模型接线。Content 和上述本机证据继续遵守仓库忽略规则，没有提交或推送。

## 迁移前已存在的诊断

以下诊断在迁移前日志中已有记录，不能把上述验证理解为全套 UE 自动化检查通过：

- `CHT_RotationOffsetCurve` 缺少 Context Object/Struct。当前 Registry 中没有其他项目资产依赖该 Chooser，默认演示验证未使用它。
- `FDebugGraphLineProperties::Color` 未显式初始化，UE 的反射属性初始化检查报错；本次保留其原有声明。
- 多个 `DDCVar.*` 控制台变量未注册，默认演示中的 Blueprint 输出相关提示；本次保留原有回退行为。

迁移前的两处 Blueprint 结构体加载错误在原生重存、重新编译后未再出现；缺失 Foley Gameplay Tag 的提示在补齐项目配置后消失。
