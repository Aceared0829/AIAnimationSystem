# 动作表示

## 概述

MotionBricks 将每一帧动作表示为经过归一化的特征向量。该表示把**根节点运动**（角色骨盆的全局位置与朝向）和**身体运动**（关节旋转、位置、速度及足部接触）分开，使根节点模型与姿态/分词器模块可以分别处理同一表示中的不同特征子集。

论文和代码中使用两个可以互相无损转换的子集：

- **全局表示**（`GlobalRootGlobalJoints`，414 维）：根节点模型主要使用它，以实现精确的全局根节点控制；数据加载器也直接返回该表示。
- **局部表示**（`LocalRootGlobalJoints`，413 维）：供姿态/分词器模块使用。

两个子集共享相同的 409 维身体特征，只是根节点的参数化方式不同：全局表示使用 5 维，局部表示使用 4 维。二者可以通过 `dual_rep.global_to_local` 和 `dual_rep.local_to_global` 无损互转。训练时，数据加载器输出全局表示，随后在送入姿态/分词器模块前即时转换为局部表示。具体而言，每个批次字典中的 `"motion"` 张量始终是**全局动作表示**，逐样本的局部转换发生在训练步骤内部。

已发布配置在 **G1Skeleton34** 参考角色骨架上使用 **DualRootGlobalJoints** 表示。这个 34 关节拓扑最初来自 Unitree G1 动作数据；由于已发布检查点依赖其精确的关节顺序，因此本分支继续保留它。每帧完整特征向量为 418 维，由 414 维全局子集与 413 维局部子集组成，二者共享 409 维身体特征。

该表示的完整推导请参阅 MotionBricks 论文。

## 特征组成

所有身体特征都在**全局坐标系（世界坐标系）**中定义。`local_vel` 中的 `local_` 是历史遗留命名：在 `DualRootGlobalJoints` 中，因为 `removing_heading=False`，速度不会根据朝向旋转，其归一化统计量也来自相同的世界坐标值。

### 身体特征（409 维）

全局根节点表示与局部根节点表示共享这些特征。

| 特征 | 维数 | 说明 |
|---|---:|---|
| `ric_data` | 99 | 33 个非根关节的全局位置；每一帧都减去根节点投影到 XZ 平面的位置，不执行朝向标准化 |
| `global_rot_data` | 204 | 全部 34 个关节在**全局（世界）坐标系**中的 6D 连续旋转表示 |
| `local_vel` | 102 | 每个关节在**全局坐标系**中的速度，通过世界位置的有限差分计算 |
| `foot_contacts` | 4 | 左脚踝、左脚趾、右脚踝、右脚趾的二值接触状态 |

### 全局根节点特征（5 维）

供根节点模型使用的全局表示子集。

| 特征 | 维数 | 说明 |
|---|---:|---|
| `global_root_pos` | 3 | 世界坐标系中的 XYZ 位置；训练和推理时，第一帧根节点的 XZ 位置会被放到原点 |
| `global_root_heading` | 2 | 根节点朝向，以绕 Y 轴旋转角的 `(cos, sin)` 表示 |

### 局部根节点特征（4 维）

供姿态/分词器模块使用的局部表示子集。它们在 `global_to_local` 转换期间由全局根节点计算得到。

| 特征 | 维数 | 说明 |
|---|---:|---|
| `local_root_rot_vel` | 1 | 绕 Y 轴的角速度 |
| `local_root_vel` | 2 | 根节点在 XZ 平面中的平移速度，以与根节点朝向对齐的坐标系表示 |
| `global_root_y` | 1 | 根节点高度，即世界坐标系中的 Y 轴位置 |

### 组合维数

| 表示 | 计算方式 | 总维数 |
|---|---|---:|
| 全局子集（`GlobalRootGlobalJoints`） | 5（全局根节点）+ 409（身体） | **414** |
| 局部子集（`LocalRootGlobalJoints`） | 4（局部根节点）+ 409（身体） | **413** |
| 完整双表示（`DualRootGlobalJoints`） | 5 + 4 + 409 | **418** |

根节点模型使用 414 维的**全局子集**；姿态/分词器模块使用 413 维的**局部子集**。

## 骨架：G1Skeleton34

骨架定义了运动学树。`G1Skeleton34` 有 34 个关节：32 个动画关节，加上 2 个用于检测足部接触的虚拟脚趾关节。

```text
pelvis（根节点）
  |-- left_hip_pitch -- left_hip_roll -- left_hip_yaw -- left_knee
  |     \-- left_ankle_pitch -- left_ankle_roll -- left_toe_base*
  |-- right_hip_pitch -- right_hip_roll -- right_hip_yaw -- right_knee
  |     \-- right_ankle_pitch -- right_ankle_roll -- right_toe_base*
  |-- waist_yaw -- waist_roll -- waist_pitch
        |-- left_shoulder_pitch -- left_shoulder_roll -- left_shoulder_yaw -- left_elbow
        |     \-- left_wrist_roll -- left_wrist_pitch -- left_wrist_yaw -- left_hand_roll
        |-- right_shoulder_pitch -- right_shoulder_roll -- right_shoulder_yaw -- right_elbow
              \-- right_wrist_roll -- right_wrist_pitch -- right_wrist_yaw -- right_hand_roll
```

`*` 虚拟脚趾关节只用于计算足部接触。

### MuJoCo 关节映射

MuJoCo 模型包含 29 个铰链关节，不包括自由浮动根节点和脚趾关节。输出的 `qpos` 向量为 36 维：

| 索引 | 内容 |
|---|---|
| 0–2 | 根节点平移 `(x, y, z)` |
| 3–6 | 根节点四元数 `(w, x, y, z)` |
| 7–35 | 29 个关节角，每个铰链关节 1 个自由度 |

`mujoco_qpos_converter` 类负责在 34 关节动作表示和 29 自由度 MuJoCo 模型之间进行映射，其中包括坐标系转换：动作空间使用 Y 轴向上、Z 轴向前；MuJoCo 空间使用 Z 轴向上、X 轴向前。

## 坐标系

| 空间 | 向上轴 | 向前轴 | 手性 |
|---|---|---|---|
| 动作空间 | Y | Z | 右手系 |
| MuJoCo | Z | X | 右手系 |

两个坐标系之间的转换关系：

- 动作空间 X = MuJoCo Y
- 动作空间 Y = MuJoCo Z
- 动作空间 Z = MuJoCo X

## 归一化

所有特征在送入模型前均进行 Z-score 归一化：

```text
normalized = (feature - mean) / sqrt(std^2 + eps)
```

其中 `eps = 1e-5`，用于保证数值稳定性。`mean.npy` 和 `std.npy` 是在训练数据集上逐维计算的，保存在各模型检查点旁的 `stats/motion/` 目录中。

## 特征计算流程

MotionBricks **不会**对特征使用固定的朝向标准化。训练时，每个动作片段会被放到原点并随机旋转朝向；推理时，朝向由调用方显式指定。模型因此能够在训练中看到所有方向的动作，无需预先统一到固定坐标系。

以下流程与 `motionlib/core/motion_reps/tools/motion_features.py` 中 `compute_motion_features` 的执行顺序一致：

```text
原始动作（局部/全局关节旋转 + 根节点平移）
    │
    ▼
计算根节点特征（compute_heading_info + compute_heading_features）：
  • 全局根节点：（根节点 XYZ、朝向 cos/sin）
  • 局部根节点：（XZ 线速度、Y 轴角速度、根节点高度）
    │
    ▼
在世界坐标系中计算身体特征（compute_position_features）：
  • ric_data        （世界关节位置 − 每帧根节点 XZ）
  • local_vel       （世界坐标系有限差分速度）
  • foot_contacts   （根据位置/速度阈值判断）
  • global_rot_data （世界坐标系 6D 旋转）
    │
    ▼
逐帧拼接为 [T, 418]，并计算 Z-score 归一化统计量
    │
    ▼
数据加载器返回归一化后的全局表示 [T, 414]
    │
    ▼
训练或推理时，对每个动作片段执行：
  1. 调用 change_first_heading(..., first_heading_angle)
     - 训练：first_heading_angle ~ Uniform(0, 2π)，随机朝向
     - 推理：first_heading_angle = 0，结果确定
     效果：旋转全部帧，使第一帧面向目标方向；同时把第一帧根节点
           的 XZ 放到原点，保留 Y/根节点高度。
  2. 如果送入姿态/分词器模块，则通过
     dual_rep.global_to_local(...) 转换为局部表示；
     该转换无损，并可通过 local_to_global 逆转。
```

推理时使用逆向流程把特征还原为关节位置和旋转，然后通过 `mujoco_qpos_converter` 映射为 MuJoCo `qpos`。
