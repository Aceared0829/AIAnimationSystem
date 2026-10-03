# Unreal 实验宿主与资产边界

`UMWSamplePreview/UMWSamplePreview.uproject` 是 UE 5.8 的实验宿主，用于逐步测试 UE 内实际推理及动画工具链，验证后再考虑正式使用；**不承担动作数据导入、清洗或数据集处理**。本仓库保存项目 `.uproject`、`Source/`、必要的 `Config/` 及独立的 `MotionWeaver` 插件源码。原 `MotionMatchingInCpp` 的 Gameplay 源码已归入项目模块 `Source/UMWSamplePreview/CommonGameplay/`，地图、角色、动画和 Blueprint 已迁入项目 `Content/`，原插件已移除。`Content/` 及 UE/IDE 生成物暂不纳入 Git；不要用 `git add -f` 绕过现有忽略规则。

项目游戏模块承接现有 CMC 角色、相机、输入、Foley 和 Traversal 代码；尚未将 `AIAnimation`、`AIAnimationMotionMatching`、模型包或推理 AnimGraph 接入该 `.uproject`。默认地图为 `/Game/Levels/DefaultLevel`，资产和原生类型的兼容重定向由项目 `DefaultEngine.ini` 维护，详见 [迁移说明](UMWSamplePreview/MOTIONMATCHING_MIGRATION.md)。已有的 `unreal-script/AIAnimation/Tools/setup_motion_matching_host.ps1` 操作另一套本机 `output/ue_cmc_host`，历史 GASP 宿主测试不算此项目的测试。后续发布资产时，需要提供与源码匹配的包、目录恢复说明、清单及校验值；干净检出缺少 Content 时不能直接运行默认地图，也不能据此宣称实际推理已经运行。

迁入项目的 `MotionMatchingInCpp` 源码保留原有版权标记和来源边界；调整目录不会改变外部代码或动画资产的授权。源码的公开收录权限由项目维护者确认，正式分发条款仍需单独注明。

外部 `D:/GameAnimationSample` 是已有数据流程使用的工程，不迁入本宿主。下列 GASP 宿主实验是独立的历史入口，也不用于证明 `UMWSamplePreview` 已完成推理接线。

## 单机 CMC 观测演示

`MotionWeaverCMCPreview` 是位于 `unreal-script/MotionWeaverCMCPreview`、仅服务于 GASP 宿主的实验插件，不修改原 `AIAnimation` 推理插件。将插件目录以项目插件方式挂载到 `GameAnimationSample/Plugins/` 后，运行 `create_cmc_preview.py` 一次，会把 GASP 默认关卡和 GameMode 复制到插件内容中，将默认 Pawn 改为现有 `SandboxCharacter_CMC`，放置低矮顶棚与 `AMotionWeaverCMCTraceActor`。脚本在目标资产已存在时拒绝覆盖。生成的 `.umap/.uasset` 依赖 GASP 资产，只保留在本机，不纳入仓库或公开分发。

演示地图是 `/MotionWeaverCMCPreview/Maps/L_CMCPreview`。在 UE 编辑器打开它后按 Play，使用原 GASP CMC 角色已有的控制方式移动/切换蹲伏。屏幕显示 CMC 的 `bWantsToCrouch` 和实际 `IsCrouched()`；青色为已执行 Actor Root，紫色是当前速度的 0.75 秒外推，**不是 CMC 真正未来轨迹、Model Root 输出或生成姿态**。停止 PIE 后，诊断 CSV 位于宿主 `Saved/MotionWeaver/`；采样名义间隔 1/30 秒，但低帧率时不补帧，不能直接作为固定 30 Hz 训练数据。

可选命令行参数 `-MotionWeaverAutoTest` 会临时用侧视相机自动验证“蹲下→顶棚下起身拒绝→离开后站起”，保存两张截图与 CSV 后退出。这个单机测试不验证监听服务器、网络回滚、Pose Token、ONNX 条件模型或脚 IK。执行记录见 [UE CMC 单机演示实验](../docs/experiments/2026-09-28-ue-cmc-preview.md)。

## B1 模型姿态接线

在同一 GASP 宿主和演示地图上运行 `add_stance_model_preview.py` 后，放置的 `AMotionWeaverStancePreviewActor` 会在指定模型时用 UE NNE DirectML 推理 B1 ONNX。源角色保持 CMC 位移与碰撞；独立 `PoseableMeshComponent` 显示模型的 79 骨姿态。原 `AIAnimation` 插件没有被修改。运行前需用 `inference/export/export_stance_pilot_onnx.py` 导出对应 `model.onnx` 与 `manifest.json`；脚本默认的本机文件夹仅对当前机器有效。

```powershell
& .\unreal-sample\Run-StanceModelPreview.ps1
& .\unreal-sample\Run-StanceModelPreview.ps1 -AutoTest
& .\unreal-sample\Run-StanceModelPreview.ps1 -AutoTest -Feedback
```

默认以 GASP 原动画作为模型历史，适合看接线与单机站蹲；`-Feedback` 是将模型可见输出回灌历史的诊断模式，已观测到明显前倾漂移，不作为可用动画模式。未来 Root 当前仅是 CMC 当前速度常量外推，非 CMC 真正未来计划或 Model Root 输出；未接 AnimGraph、脚接触/IK 或网络。完整结果和原始 CSV 见 [UE B1 在线预览实验](../docs/experiments/2026-09-28-ue-b1-online-preview.md)。
