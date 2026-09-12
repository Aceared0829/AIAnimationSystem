# 后训练扩展位置

当前尚无独立后训练实现。后续微调、蒸馏等入口放在这里，共用 `model/`、`data/` 和 `training/common/`，避免复制模型与数据转换代码。

现有同数据契约续训仍由 `training/pretrain/train_unreal.py --resume` 执行。
