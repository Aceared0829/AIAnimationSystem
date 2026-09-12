# 训练

`pretrain/`：现有 VQ-VAE、Pose、Root 初始训练与同契约续训入口。`train_unreal.py` 读取自己的 UE 数据；另外三个脚本保留上游合成数据冒烟用途。

`posttrain/`：后训练扩展位置；当前没有独立微调、蒸馏或强化学习算法。`--resume` 恢复优化器和步数，不等同于新任务后训练。

`models/`：Lightning 训练封装，兼容旧 `motionbricks.vqvae.models` 和 `motionbricks.motion_backbone.models` 名称。

`common/`：原生帧掩码、质量损失、采样器、优化器工具，保留旧检查点所需别名。

`evaluation/`：质量评估、容量诊断与评估画廊。`configs/` 保留训练配置。`runs/` 保存本地实验与检查点，不提交 Git。

入口：`python -m training.pretrain.train_unreal --help`。Pose-only 数据继续禁止 Root 训练；训练后使用 `inference/export/` 导出推理包。
