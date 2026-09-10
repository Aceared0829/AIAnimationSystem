# AIAnimationSystem 混合运动与生成姿态开发方案

日期：2026-09-09
状态：方案 v2。Schema v2 数据与训练契约已实现；UE Runtime、IK/warping、CMC/Mover 适配和联机验证待实现。

本文属于 [AIAnimationSystem](../../README.md)。当前实现边界见 [插件说明](README.md)，规划能力不能作为已完成功能声明。

## 1. 总体架构

项目不采用 Only CMC/Mover，也不允许模型直接覆盖 Actor 世界变换，而是按动作选择三种模式：

| 模式 | 动作 | 位移来源 | 最终权威 |
| --- | --- | --- | --- |
| Velocity Driven | Walk、Run、Sprint、普通转向 | 输入和 Movement 模拟 | CMC/Mover |
| Root Motion Assisted | 起步、急停、Pivot、短 Dash | 模型/动画 Root Delta 建议 | Movement 校验后的 Delta |
| Root Motion Action | Vault、Mantle、Slide、Roll、Get Up、固定交互 | 动画或模型 Root 轨迹 | RootMotionSource/Mover 与服务器许可 |

```text
普通移动：输入 → CMC/Mover → 权威胶囊轨迹
                                ↓
                    相对姿态 + 步态相位/接触
                                ↓
          Distance/Stride/Orientation Warping + Foot Lock/IK

受控动作：动作与环境目标 → 服务器/Movement 验证
                                ↓
               ProposedRootMotion + 相对姿态
                                ↓
       RootMotionSource/Mover + Motion/Traversal Warping + 手脚 IK
```

模型可以提出 Root Motion，但只能输出 `ProposedRootDelta`。Movement 层根据碰撞、坡度、速度、移动模式和服务器规则得到 `AcceptedRootDelta`。同一段运动只有一个位移所有者，禁止模型、Montage 和 Movement 重复施加位移。

## 2. Root 与 Pelvis 契约

| 数据 | 空间 | 所有者 |
| --- | --- | --- |
| `AuthoritativeRoot` | UE 世界/Movement 空间 | CMC/Mover |
| `ProposedRootDelta` | 上一 Root 或动作锚点局部空间 | 模型/动画，非权威 |
| `AcceptedRootDelta` | Movement 模拟空间 | CMC/Mover |
| Pelvis 与身体关节 | UE Root 局部空间 | 姿态模型 |
| IK 目标 | 明确声明的世界、组件或骨骼空间 | Gameplay/环境查询 |

当前 Schema v2 已将 `root_frames` 保存为只读审计轨道，`frames` 保存 UE Root 局部空间中的 Pelvis 子树，训练契约为 `pose_only_root_authoritative`。下一版若训练 Root Motion，应增加独立 `root_motion_proposal_v1` 目标和输出头，不能把 Root 位移重新混入 Pelvis。

Runtime 输入至少包含实际/期望速度与朝向、加速度、MovementMode、地面法线、移动基座、跳跃阶段、未来轨迹、时间戳和网络纠正版本。Interaction 额外输入动作阶段、物体变换、双手/双脚目标和表面法线。

模型输出至少包含契约版本、骨架签名、时间戳、Root-relative Pelvis、身体关节、双脚/双手接触、步态相位、置信度，以及可选 `ProposedRootDelta`。Runtime 必须能忽略 Root 建议而正确播放相对姿态。

## 3. 防滑步闭环

Only CMC 不会自动消除滑步，Root Motion 也无法自动解决碰撞修正后的滑步。系统必须组合：

1. 模型以 CMC/Mover 的真实速度和未来轨迹为条件，不按输入键值猜速度。
2. 步态相位和接触概率使用迟滞，避免支撑脚反复锁定。
3. Distance Matching 控制起步、急停和落地事件发生的距离。
4. Stride Warping 让步幅匹配实际速度，Orientation Warping 匹配移动方向。
5. Foot Lock 在支撑阶段固定世界空间脚点，Foot IK 处理地面残差。
6. Warping 或 IK 超限时重选动作、重新生成或回退，不能无限拉伸骨骼。

```text
FootSlipCm = 支撑阶段脚底世界空间累计位移
RootAcceptanceErrorCm = ProposedRootDelta 与 AcceptedRootDelta 的累计差
WarpScale = 实际步长 / 模型期望步长
IKCorrectionCm = IK 前后末端位置差
```

跳跃、传送、网络大修正和移动基座失效时必须释放或重建脚锁。Pelvis IK 只修正网格表现，不能反向推动胶囊。

## 4. IK 与特殊动作

AnimGraph 推荐顺序：相对姿态基底 → 骨轴恢复/重定向 → Distance/Stride/Orientation Warping → Pelvis 修正 → 双脚 IK → Traversal/Interaction 对齐 → 双手 IK → 关节范围与异常值钳制。

手部精确接触必须依赖 Gameplay 提供的目标；模型只生成接触意图和相对姿态。IK 修正过大表示上游姿态、目标或移动轨迹不匹配，应记录失败并回退。

Interaction 优先补充物体变换、手部目标和接触阶段，并拆分混杂动作类别，不直接扩容。Ragdoll 由 Chaos/Physical Animation 负责真实物理过程；模型负责受击过渡、物理结束后的 Get Up 选择和受控 Root Motion，不取代布娃娃模拟。

## 5. Runtime 模块与线程

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `AILocomotionCore` | 公共契约、骨架签名、模型元数据 | 待实现 |
| `AILocomotionDatasetEditor` | UE 资产检查与 Schema v2 导出 | 已有实验实现 |
| `AILocomotionRuntime` | 姿态缓冲、推理调度、时间戳、回退、AnimInstance 数据 | 待实现 |
| CMC Adapter | CMC 状态、Root Motion、预测与纠正 | 待实现 |
| Mover Adapter | Mover 状态、模拟与回滚通知 | 待实现 |

GameThread 采集 UObject、Movement、碰撞和地面状态；纯数值推理可以异步。请求必须包含时间戳、状态版本和取消语义。AnimInstance 在 GameThread 缓存数据，worker thread 只读取 Proxy/普通数据，不调用非线程安全 UObject API。传送、重生、网络纠正和模式突变使旧结果失效。

模型不必 60 Hz 运行。用 10/15/20/30 Hz 推理配合 60 Hz 插值进行实测；超时后平滑回退传统动画，角色移动必须继续正常工作。

## 6. 多人联机

服务器决定胶囊移动、碰撞、移动模式、Root Motion Action 许可和关键目标。自主代理使用 CMC/Mover 预测并本地生成视觉姿态；影响实际移动的 Root Motion Assisted 输入必须进入 SavedMove 或对应 Mover 回滚状态。模拟代理依据复制后的 Movement 状态和动作事件生成姿态，不逐骨骼复制。

模型 Root Motion 参与实际位移时，必须由服务器或引擎已有预测路径验证和重演。随机种子不能代替网络预测协议。CMC 与 Mover 必须分别提供真实实现证据，不能用公共接口占位宣称支持。

## 7. 指标重新定义

Schema v2 现有 `World RMSE` 不再代表 CMC/Mover 世界轨迹，应重命名为 `ReconstructedJointRMSECm`。评估拆为：

- 姿态层：Pelvis-relative Joint RMSE/P95、旋转误差、pelvis/双脚/双手误差、接触 F1。
- Movement 层：胶囊位置/朝向、起跳点、落地点、RootAcceptanceError、网络纠正距离和恢复时间。
- 最终角色层：Final Joint World RMSE、FootSlip、穿透/悬空、手部目标误差、IK 修正和异常帧率。
- 性能层：权重和常驻内存、CPU/GPU P50/P95/P99、AnimGraph/IK 成本、多角色吞吐、超时与回退次数。

训练 loss、离线姿态 RMSE 和旧 `World RMSE` 均不能单独证明 UE Runtime、Root Motion 或联机效果。

## 8. 模型容量与 Runtime 预算

当前 25.4M Pose VQ-VAE 作为基线，不立即扩容。理论纯权重约为 FP32 102 MB、FP16 51 MB、INT8 25 MB，实际还包括激活、缓存和推理后端。

优先顺序为：修复数据/标签 → 增加必要条件 → 困难类别采样或专门分支 → 测推理频率与批处理 → FP16/INT8、裁剪和蒸馏 → 最后才小幅调整 codebook、latent 或网络宽度。

扩容必须同时报告精度、模型大小、单角色延迟和多角色吞吐。初始实验目标为 Runtime 权重约 64 MB 内、单近景角色平均推理低于 2 ms、4 个近景角色总推理低于 4 ms、插值与 IK 单角色低于 0.5 ms；最终阈值以目标硬件实测为准。

## 9. 分阶段实施与验收

### A. 指标与契约

重命名 `World RMSE`，实现 Runtime C++ 公共结构、版本/骨架/单位校验和 Schema v2 往返预览。验收：Root、相对姿态和最终世界姿态可独立查看，错误契约无法加载。

### B. 无模型 Runtime 闭环

用录制的 Schema v2 相对姿态回放，建立 CMC → AnimGraph 最小链路、Debug Draw 和传统动画回退。验收：胶囊与网格没有 Root/Pelvis 双重位移，传送和模式切换不会消费过期姿态。

### C. Locomotion 防滑步

实现相位、接触、Distance Matching、Stride/Orientation Warping、Pelvis 与 Foot IK。对 Walk/Run/Sprint/Start/Stop/Pivot/坡面/台阶分别输出 FootSlip 和修正量。

### D. 受控 Root Motion

实现三种运动模式、Proposed/Accepted Root Delta 记录，以及 Vault/Mantle/Slide/Get Up 的 CMC Root Motion 和 Motion/Traversal Warping。验收：碰撞不穿透、取消可恢复、Root 只应用一次。

### E. Interaction 与模型推理

增加双手目标与 Hand IK，接入当前 25.4M 模型的异步请求、版本、取消和超时回退。先完成 FP32/FP16 与多角色 Unreal Insights 基线，再决定量化、蒸馏或容量实验。

### F. 联机与 Mover

完成 CMC 自主代理、模拟代理、服务器验证，以及延迟、丢包、网络纠正和 Root Motion Action 测试；随后完成 Mover 的真实适配与回滚验证。

### G. 困难类别与容量决策

逐样本分析 Interaction/Ragdoll，比较数据、条件、采样、专门分支和小幅容量实验。没有欠拟合证据和 Runtime 预算，不扩大主模型。

## 10. CR 与证据要求

每阶段依次执行静态契约检查、UE 5.8 编译、聚焦自动化、真实资产往返、运行场景与 Unreal Insights、代码审查和修复后回归。分别报告静态检查、编译、自动化、Runtime 和联机证据；编辑器打开、训练完成或命令退出不能替代最终蒙皮和联机验证。

下一轮从阶段 A 开始，再做阶段 B 和 C。先证明坐标、Movement、姿态和 IK 的责任边界与防滑步闭环，之后接入 Root Motion Action 和真实模型 Runtime。

## 参考

- [Epic：Character Movement Component](https://dev.epicgames.com/documentation/en-us/unreal-engine/character-movement-component?application_version=5.6)
- [Epic：Mover](https://dev.epicgames.com/documentation/unreal-engine/mover-in-unreal-engine)
- [MotionBricks 论文](https://arxiv.org/abs/2604.24833)

底层机制以项目实际使用的 UE 5.8 源码为最终依据；本文的职责、契约、阶段和门槛是 AIAnimationSystem 当前工程决策。
