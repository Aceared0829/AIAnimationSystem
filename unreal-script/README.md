# Unreal 集成

`AIAnimation/` 是 **Inference Lab 实验插件**：用于模型重建效果、动画工作线程 GPU 推理及性能测试。它不是正式游戏运行时实现；使用说明与实测结果见 [实验说明](AIAnimation/README.md)。

`AILocomotionSystem/AILocomotionDataset/` 是现有编辑器插件，保留插件、模块、反射类型及 Content 挂载名称。

把完整 `AILocomotionDataset/` 文件夹复制到目标工程的 `Plugins/AILocomotionDataset/`，然后构建 Editor 目标。不要把外层说明目录当成插件根目录。

`python/` 是在 UE 宿主内运行的导出、重定向和验证脚本；宿主外的数据调度工具归 `data/tools/`。
