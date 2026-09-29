# Unreal 示例工程边界

当前仓库没有独立 `.uproject` 示例工程。外部 `D:/GameAnimationSample` 是现有数据流程使用的工程，未搬入此仓库。

将来示例在这里按项目名保存 `.uproject`、`Source/` 和 `Config/`；通过 `unreal-script/` 插件组装功能。示例 `Content/` 应由匹配版本、带清单和 SHA-256 的资产包恢复。

当前没有为该目录发布 Content Release；不能仅凭仓库内源码宣称在没有 GASP 资产的机器上可打开地图或运行游戏。

## 单机 CMC 观测演示

`MotionWeaverCMCPreview` 是仅服务于 GASP 宿主的实验插件，不修改原 `AIAnimation` 推理插件。将插件目录以项目插件方式挂载到 `GameAnimationSample/Plugins/` 后，运行 `create_cmc_preview.py` 一次，会把 GASP 默认关卡和 GameMode 复制到插件内容中，将默认 Pawn 改为现有 `SandboxCharacter_CMC`，放置低矮顶棚与 `AMotionWeaverCMCTraceActor`。脚本在目标资产已存在时拒绝覆盖。生成的 `.umap/.uasset` 依赖 GASP 资产，只保留在本机，不纳入仓库或公开分发。

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
