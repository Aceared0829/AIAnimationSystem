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

## 条件训练优化实验

保持同一冻结数据、训练/验证/测试划分与模型宽度。新训练器默认仍用旧版均匀窗口采样和固定候选参考位置；新增的开关用于**逐项对照**：

- `--sampling balanced`：按类别窗口数及片段窗口数的平方根倒数加权，仍从原有训练窗口抽取，不增加数据，不改变验证/测试集。`--category-power`、`--clip-power` 控制加权强度。
- `--reference-sampling diverse`：训练时采样 0–3 个不同时间的全身硬参考帧；输出依然精确覆盖参考帧。单帧局部骨骼参考尚未由本模型支持。
- `--reference-sampling hybrid`：一半窗口维持旧版固定时点参考采样，另一半采用分散时点采样；用于检验非固定时点收益能否与旧场景质量兼得。
- `--contact-weight 0.01`：以封版中的启发式脚部接触标签，约束真实 Root 合成后的接触脚速度。仅用于受控实验，权重不应直接视为最优值。

每轮保存 Python、NumPy、Torch、CUDA 和采样器随机状态；新检查点续训可以复现采样顺序。旧检查点没有这些状态，续训时会提示无法逐步复现。可用 `python -m training.evaluation.evaluate_conditioned_quality --split validation ...` 在验证集每条动作的中心窗口评估无参考、单参考、双参考和非固定时点参考，并按类别输出位置、旋转、速度与接触脚速度。该评估仍使用源动画未来 Root，接触标签也由源动作启发式派生；测试集仅在候选方案确定后运行一次。

2026-09-25 的云端对照、选定权重及冻结测试结果见 [conditioned_optimization_20260925.md](conditioned_optimization_20260925.md)。
