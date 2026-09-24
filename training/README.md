# 训练

`pretrain/`：现有 VQ-VAE、Pose、Root 初始训练与同契约续训入口。`train_unreal.py` 读取自己的 UE 数据；另外三个脚本保留上游合成数据冒烟用途。

`posttrain/`：后训练扩展位置；当前没有独立微调、蒸馏或强化学习算法。`--resume` 恢复优化器和步数，不等同于新任务后训练。

`models/`：Lightning 训练封装，兼容旧 `motionbricks.vqvae.models` 和 `motionbricks.motion_backbone.models` 名称。

`common/`：原生帧掩码、质量损失、采样器、优化器工具，保留旧检查点所需别名。

`evaluation/`：质量评估、容量诊断与评估画廊。`configs/` 保留训练配置。`runs/` 保存本地实验与检查点，不提交 Git。

入口：`python -m training.pretrain.train_unreal --help`。Pose-only 数据继续禁止 Root 训练；训练后使用 `inference/export/` 导出推理包。

## Root 路径 + 硬参考姿态条件生成

`pretrain/train_conditioned_pose.py` 是独立于旧 VQ-VAE/Pose 任务的首版训练器。它只读取已封版的 `reference_guided_root_pose_v1` 契约，以历史姿态、独立 Root 路径及稀疏全身参考姿态为条件，预测未来 24 帧 Root 相对关节位置与 6D 旋转。训练只使用 train 窗口，validation 用来观察泛化；硬参考帧在输出端精确覆盖。训练时从原始 NPZ 逐条校验哈希并缓存，不把相互重叠的 26,861 个窗口复制为另一份数据。当前 Root 路径取自源动作，是离线理想条件，不代表游戏输入或 Root 规划器效果。

```powershell
& .venv\Scripts\python.exe -m training.pretrain.train_conditioned_pose `
  --release 'E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924' `
  --lock 'data\freezes\reference_guided_root_pose_v1_20260924.json' `
  --output 'E:\AIAnimationSystemData\training_runs\<new-run>' --epochs 5 --batch-size 8
```

`--resume <epoch_NNN.pt>` 可从同一契约、宽度和 batch size 的检查点继续到新的总轮数。训练输出包括配置、逐轮指标和检查点。日志中的 `pose_axis_rmse_cm` 是**单坐标轴**均方根误差；首批运行记录使用旧字段名 `pose_rmse_cm`，口径相同。与非学习基线比较时，必须运行 `evaluation/evaluate_conditioned_pose.py`，用测试集每条动作的中心窗口计算**三维关节距离**非参考帧 RMSE，避免混用口径。当前仍需后续处理旋转矩阵正交化、骨长、脚接触、UE 蒙皮及实际控制输入。
