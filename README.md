# MotionBricks 游戏动画精简版

新增 [AILocomotionSystem 动画数据插件](Unreal/AILocomotionSystem/README.md)：在 Unreal 中选择 `AnimSequence`，导出角色骨架与动作数据，再通过独立 Python 入口训练适配该骨架的模型。包含编辑器导出、数据预处理和检查点保存；运行时推理插件尚未实现。

[AILocomotionSystem 完整开发方案](Unreal/AILocomotionSystem/LocomotionPlan.md)：以多人联机为默认需求，由 CMC / Mover 驱动移动，统一人形模型生成姿态，通过重定向适配角色；第一阶段覆盖 Locomotion、跳跃与蹲伏。该文档描述已确认的开发方向，不代表功能已经完成。

**该插件当前为实验性实现：真实 UE 动画资产的导出及完整训练可用性尚未验证。** 已通过的编译和 CPU 小网络测试不代表真实项目训练已可用。`codex/game-development-only` 作为主分支，本功能在独立开发分支维护。

本分支已经移除机器人控制与硬件部署模块，只保留可用于游戏开发、实时角色动画和动作生成研究的 MotionBricks。

[MotionBricks 技术文档](motionbricks/README.md) · [中文交互界面](motionbricks/docs/chinese_interface.md) · [动作表示](motionbricks/docs/motion_representation.md) · [引用与许可说明](引用与许可说明.md)

## 分支定位

保留内容包括：

- 实时神经角色动作生成；
- 键盘驱动的移动与动作风格切换；
- Root Motion 与全身骨骼姿态生成；
- 使用 VQ-VAE 将连续动作编码为离散动作 Token；
- 骨骼层级、前向运动学、旋转和坐标系工具；
- 自定义动作数据集和骨骼重定向；
- 使用 MuJoCo 实时预览生成的角色动作；
- 预训练模型、训练配置和合成数据训练脚本。

MuJoCo 和 Unitree G1 骨架仍然存在，但这里只把它们当作“动画预览器”和“参考骨架”。现有预训练权重与该骨骼拓扑绑定，因此不能在不重新训练或重定向的情况下直接删除。

## 已删除内容

- GEAR-SONIC 机器人强化学习训练系统；
- Decoupled WBC 机器人全身控制；
- Unitree SDK、电机指令、DDS 通信和真机安全检查；
- TensorRT 真机策略部署；
- VR 机器人遥操作；
- VLA 数据采集和机器人推理；
- 相机服务、ROS、JetPack、systemd 和机器人 Docker 环境；
- 真机安装脚本、机器人专用媒体与第三方二进制依赖；
- 与上述模块对应的英文文档。

原始内容仍可在 Git 的 `main` 分支中找到。

## 建议学习顺序

1. 阅读 `motionbricks/docs/motion_representation.md`，理解骨骼、Root Motion、局部姿态和动作特征。
2. 运行 `motionbricks/scripts/interactive_demo_g1.py`，观察玩家输入怎样改变动作。
3. 阅读 `motion_backbone/demo/controllers.py`，理解输入层。
4. 阅读 `motion_backbone/inference/motion_inference.py`，理解逐帧生成流程。
5. 阅读 `vqvae/`，理解动作 Token。
6. 使用合成数据运行三个训练脚本。
7. 最后根据 `adding_your_own_dataset.md` 接入自己的角色骨骼与动画数据。

## 快速开始

需要 Python 3.10、支持 CUDA 的显卡和 Git LFS。

```bash
git lfs install
git lfs pull --include="motionbricks/out/**" --exclude=""
git lfs pull --include="motionbricks/assets/skeletons/g1/meshes/**" --exclude=""

cd motionbricks
conda create -n motionbricks python=3.10 -y
conda activate motionbricks
pip install -e .
python scripts/interactive_demo_g1.py
```

交互演示默认启用中文界面。在 Windows 上，中文控制栏和 MuJoCo 3D 画面会嵌入同一个主窗口；其他系统无法使用 Win32 窗口嵌入时，会回退为中文控制窗口与 3D 窗口分离显示。完整说明与故障排查参见[中文交互界面](motionbricks/docs/chinese_interface.md)。

Windows 用户在完成虚拟环境和模型权重配置后，也可以直接双击仓库根目录的 `MotionBricks.exe`。该启动器不会显示控制台窗口，会从项目自带的 `.venv` 启动中文单窗口演示。启动器源码、图标、桌面快捷方式设置及重新构建方法同样记录在[中文交互界面](motionbricks/docs/chinese_interface.md)中。

训练入口：

```bash
cd motionbricks
python scripts/train_vqvae.py
python scripts/train_pose.py
python scripts/train_root.py
```

## 接入 Unity 或 Unreal 的关键工作

当前代码不会直接输出 Unity `AnimationClip` 或 Unreal `AnimSequence`。Unreal 后续接入按上述开发方案实施，运行时桥接层尚未实现：

```text
玩家 / AI 输入
  → CMC 或 Mover 移动模拟
  → 实际运动状态与未来轨迹条件
  → 统一人形模型生成姿态
  → 目标角色重定向与接触修正
  → Unreal 骨骼姿态
```

需要处理骨骼语义、参考姿态、坐标系、单位、脚底接触和网络纠正。先用真实资产验证采样与还原，再接入运行时。G1 仅作为已有参考及迁移实验候选；当前自定义 UE 训练入口不支持直接加载 G1 权重微调。Unity 接入不在本次 Unreal 方案范围内。
