# 数据

`runtime/`：可安装的数据加载器、骨架与交换契约，保留 `motionbricks.data` 导入名称。

`tools/`：数据准备、格式校验、批次调度、人工审核服务和入库工具。`review_web/` 随审核服务归档。`validate_seed_training.py` 校验训练数据格式，属于数据验收，不执行梯度训练。

`raw/` 与 `prepared/`：本地数据，忽略提交。当前大数据物理目录为 `E:/AIAnimationSystemData/`，包括 `BONES-SEED/`、`MotionDataLibrary/`、`UE/AILocomotionDataset/` 和 `prepared/`；旧 D 盘入口可能是兼容 Junction，不能视为第二份数据。

已有 UE 导出数据的 Root/姿态条件索引与非学习基线全部使用 Python 离线处理，无需启动完整 UE 编辑器。契约、实测数量、局限和复现命令见 [Root 驱动与硬参考姿态数据契约](../docs/reference-guided-data-contract-v1.md)。新资产的采样或跨骨架重定向仍依赖 UE 资产系统，可走已有无界面批处理；编辑器用于最终视觉验收。

根目录安装后运行：`python -m data.tools.prepare_unreal_dataset --help` 或 `python -m data.tools.motion_review_server --help`。
