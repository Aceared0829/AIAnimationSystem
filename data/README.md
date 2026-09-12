# 数据

`runtime/`：可安装的数据加载器、骨架与交换契约，保留 `motionbricks.data` 导入名称。

`tools/`：数据准备、格式校验、批次调度、人工审核服务和入库工具。`review_web/` 随审核服务归档。`validate_seed_training.py` 校验训练数据格式，属于数据验收，不执行梯度训练。

`raw/` 与 `prepared/`：本地数据，忽略提交。既有 UE 转换结果已移至 `prepared/`；外部 `D:/MotionDataLibrary` 与 `D:/BONES-SEED` 仍由原有流程使用。

根目录安装后运行：`python -m data.tools.prepare_unreal_dataset --help` 或 `python -m data.tools.motion_review_server --help`。
