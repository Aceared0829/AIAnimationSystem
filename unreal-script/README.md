# Unreal 集成

`AIAnimation/` 是 **Inference Lab 实验插件**：用于模型重建效果、动画工作线程 GPU 推理及性能测试。它不是正式游戏运行时实现；使用说明与实测结果见 [实验说明](AIAnimation/README.md)。

`AILocomotionSystem/AILocomotionDataset/` 是现有编辑器插件，保留插件、模块、反射类型及 Content 挂载名称。

把完整 `AILocomotionDataset/` 文件夹复制到目标工程的 `Plugins/AILocomotionDataset/`，然后构建 Editor 目标。不要把外层说明目录当成插件根目录。

`python/` 是在 UE 宿主内运行的导出、重定向和验证脚本；宿主外的数据调度工具归 `data/tools/`。

## MotionWeaver 插件镜像

`unreal-sample/UMWSamplePreview/Plugins/MotionWeaver/` 是 MotionWeaver 的唯一开发源。`unreal-script/MotionWeaver/` 是面向其他 UE 宿主和集成流程的同步镜像；日常开发直接修改 Sample 插件，不要在镜像目录单独修复代码。

在合并包含 Sample 插件变更的分支时，运行以下命令把源插件同步到镜像，然后将同步结果作为同一批次提交：

```powershell
& .\unreal-script\Tools\Sync-MotionWeaver.ps1
& .\unreal-script\Tools\Sync-MotionWeaver.ps1 -Check
```

同步脚本只复制插件源码和元数据，排除 `Content/` 和 `Binaries/`、`Intermediate/`、`Saved/` 等 UE 生成物，并删除镜像中已从源插件移除的文件。它拒绝通过非排除目录中的 Junction 或其他链接读写、删除文件；保留排除目录和空目录。`-Check` 返回非零状态时，说明合并前镜像尚未同步。
