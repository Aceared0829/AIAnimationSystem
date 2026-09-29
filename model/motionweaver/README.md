# MotionWeaver

MotionWeaver 是 AIAnimationSystem 中面向 UE 实时角色运动的**目标模型名称**。截至 2026-09-28，已新增 [`MotionWeaverInference`](../../inference/runtime/motionweaver.py) 的给定 Actor Root 姿态推理入口，并在 A800 从零训练了 20,000 步 Pose Token 权重。该权重已在本地完成骨架推理评估，尚未达到脚滑、Run/Crouch 姿态和 CMC 蹲伏响应的质量门槛，也没有 UE 可用推理包。当前玩家试玩仍加载 `ReferenceGuidedPose` 导出的 ONNX；不能仅将该模型改名为 MotionWeaver。

MotionWeaver 将以相邻的 [`model/motionbricks/`](../motionbricks/) 为模型基础，复用并适配其多头 VQ-VAE、Pose Token 网络和条件解码器。原版 MotionBricks 源码、G1 演示和权重保留原路径。UE 79 骨需要自己的数据契约和训练权重，不能直接使用 G1 检查点。

MotionWeaver 支持三种运动来源：CMC、Mover 或模型生成的动画 Root motion。前两者给出轨迹，模型据此生成姿态；模型驱动时推理产生 Root motion 与配套姿态，UE 运动执行层处理碰撞、约束与最终位移，并把实际结果反馈给后续推理。每个更新步只有一个实际位移结果，姿态必须和该结果对齐。当前入口只实现“给定 Root → Pose Token → 解码”的源码编排；模型 Root 生成与 UE 运动执行尚未接入。模型姿态与实际 Root 的误差必须在蒙皮闭环中核对。

实现和训练门槛见 [MotionWeaver 架构对比与迁移计划](../../docs/motionweaver-architecture.md)，20,000 步训练与本地推理结果见 [Actor Root 实验记录](../../docs/experiments/2026-09-28-motionweaver-a800-actor-root.md)。当前适配器已通过真实 UE VQ-VAE 和 Pose 权重的本地推理测试；UE 内 NNE、角色蒙皮和实时玩家闭环尚未执行。
