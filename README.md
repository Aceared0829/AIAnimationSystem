# MotionBricks 游戏动画精简版

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

当前代码不会直接输出 Unity `AnimationClip` 或 Unreal `AnimSequence`。接入游戏引擎时需要增加一个导出/运行时桥接层：

```text
玩家输入
  → MotionBricks 条件输入
  → Pose + Root Motion
  → 从 G1 骨架重定向到游戏角色骨架
  → 坐标系与单位转换
  → Unity/Unreal 骨骼变换
```

需要特别处理骨骼名称映射、T-Pose 差异、左右手坐标系、根节点朝向、单位缩放和脚底锁定。建议先导出离线动画验证重定向，再实现实时推理插件。
