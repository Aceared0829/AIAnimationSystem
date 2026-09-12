# 添加自定义数据集

> 修改说明：AIAnimationSystem 维护者基于 NVIDIA MotionBricks 上游文档翻译并调整了本文。原始项目来源与许可见[引用与许可说明](../../引用与许可说明.md)。

开放动作数据集可从 <https://bones.studio/datasets> 获取。本指南介绍如何将自己的角色动作数据接入 MotionBricks 训练。

## 两种接入方式

接入自己的数据时有两种选择：

1. **建立自己的训练管线，不依赖 MotionBricks 的动作表示处理器和数据加载器（强烈推荐）。** MotionBricks 的动作分词器、根节点模型和姿态模型并不限制必须使用哪一种动作表示。建议参考当前的合成数据训练路径建立自己的训练管线。

2. **复用 MotionBricks 动作数据表示。** 这种方式假设继续使用相同的 `G1Skeleton34` 表示，只替换为采用同样流程处理的另一套数据集。完整表示规范见[动作表示](motion_representation.md)。

---

## 复用 MotionBricks 表示

编写一个 PyTorch `Dataset`，使其 `__getitem__` 返回：

```python
{"keyid": int, "motion": Tensor[T, feature_dim]}
```

其中，`motion` 是单个动作片段**已经计算并完成归一化**的全局动作特征张量。特征布局以及如何从原始关节旋转和全局位置生成该张量，参见[动作表示](motion_representation.md)。

你可以复用项目提供的归一化统计量，但更建议根据自己的数据计算统计量。

最小数据集接口可参考 `motionbricks/data/synthetic_dataset.py`。

## 自定义完整实现

对于绝大多数非 G1 数据集，**强烈建议**自己编写数据加载器和动作表示处理器，不要强行套用现有实现。

### 代码入口

| 要实现的内容 | 建议起点 |
|---|---|
| 新动作表示类 | `motionbricks/motionlib/core/motion_reps/motion_reps_base/motion_rep_base.py` 中的 `MotionRepBase`，这是只负责连接归一化逻辑的最小基类 |
| 根节点与身体分离的表示 | `motionbricks/motionlib/core/motion_reps/motion_reps_base/seperate_root_local_body.py` |
| 完整双根节点示例 | `motionbricks/motionlib/core/motion_reps/dual_root_global_joints.py`，它构建 `GlobalRootGlobalJoints`、`LocalRootGlobalJoints` 和 `DualRootGlobalJoints` |
| 实际特征计算（FK、速度、朝向） | `motionbricks/motionlib/core/motion_reps/tools/motion_features.py`，重点查看 `compute_motion_features` 以及它调用的各个特征辅助函数 |
| 最小数据加载器 | `motionbricks/data/synthetic_dataset.py` 中的 `SyntheticMotionDataset` 和 `collate_batch` |
| 统计量处理 | `motionbricks/motionlib/core/utils/stats.py` 中的 `Stats` |
