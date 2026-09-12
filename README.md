# AIAnimationSystem

面向 Unreal Engine 的 AI 角色动画实验项目，探索从动画数据训练到实时姿态生成的完整流程。

本项目基于 NVIDIA [GR00T-WholeBodyControl](https://github.com/NVlabs/GR00T-WholeBodyControl) 仓库中的 [MotionBricks](https://nvlabs.github.io/motionbricks/) 开发，由本仓库独立维护。MotionBricks 的模型架构、动作表示、原有训练与推理代码、预训练权重和上游演示属于原项目成果；本项目在其基础上面向游戏动画做裁剪、中文交互界面与 Windows 启动器适配，并添加实验性的 UE 动画导出和自定义骨架训练入口。

> **实验阶段：** 已有 UE 数据、训练与 FP32 导出工具；历史实验见插件说明，本次目录迁移验收见仓库结构文档。UE 运行时推理和 AnimGraph 输出尚未实现。本项目不代表 NVIDIA 官方产品，也不表示获得 NVIDIA 的认可或背书。

当前先完成 Locomotion、跳跃和蹲伏的数据与动画流程；项目名称覆盖更广泛的角色动画方向，后续动作范围以开发方案与实际验证为准。

[UE 插件与训练](unreal-script/AILocomotionSystem/README.md) · [第一阶段开发方案](unreal-script/AILocomotionSystem/LocomotionPlan.md) · [MotionBricks 演示与技术说明](docs/motionbricks/README.md) · [来源、引用与许可](引用与许可说明.md)

## 当前进度

| 内容 | 当前状态 |
| --- | --- |
| MotionBricks G1 参考演示 | 保留上游模型与 MuJoCo 预览流程，增加中文界面和 Windows 启动器；不等同于 UE 运行时效果 |
| UE 动画导出 | 已有实验性 `AILocomotionDataset` 编辑器插件，从 `AnimSequence` 导出骨架和动作数据 |
| 自定义 UE 骨架训练 | 已有数据预处理、VQ-VAE / Pose / Root 训练、检查点保存与续训入口 |
| 已记录的验证 | UE 5.8.2 编译与链接、程序生成动画夹具上的 CPU 小网络训练测试；详见插件说明 |
| 真实资产与生成质量 | 历史实验见插件的 TrainingResults；本次迁移使用受控夹具验证功能，不重新评定真实动作生成质量 |
| UE 运行时动画 | 推理、AnimGraph 输出、统一人形重定向，以及 CMC / Mover 与联机接入均为后续工作 |

现有 G1 权重与参考骨架绑定。自定义 UE 训练入口不支持直接加载 G1 权重微调，原 G1 演示也不能直接预览新的 UE 骨架检查点。

## 快速开始

### 获取仓库

安装 Git LFS 后执行：

```bash
git lfs install
git clone https://github.com/Aceared0829/AIAnimationSystem.git
cd AIAnimationSystem
```

当前开发主线为 `codex/game-development-only`，也是默认分支。预训练检查点默认不自动下载；按下面的使用场景准备环境和模型。

### UE 动画导出与训练

将 `unreal-script/AILocomotionSystem/AILocomotionDataset/` 复制到 UE 项目的 `Plugins/AILocomotionDataset/`，编译 Editor 目标并启用 **AI Locomotion Dataset**。在编辑器中选择动画资产，通过 **工具 → AI Locomotion：导出选中动画** 生成训练数据。

Python 训练环境使用 Python 3.12；完整安装命令、骨架要求、预处理与训练命令见 [UE 插件与训练说明](unreal-script/AILocomotionSystem/README.md)。这条路线使用自己的动画数据，不需要下载 G1 演示权重。

`AILocomotionSystem` 与 `AILocomotionDataset` 目前仍是插件目录和技术标识；仓库对外名称为 **AIAnimationSystem**。

### MotionBricks 参考演示

该演示使用 G1 参考骨架、MuJoCo 和预训练权重。按现有演示环境说明准备 Python 3.10、支持 CUDA 的显卡及依赖，在仓库根目录执行：

```bash
git lfs pull --include="model-weight/base/motionbricks/**" --exclude=""
git lfs pull --include="inference/assets/skeletons/g1/meshes/**" --exclude=""
# 以下命令在仓库根目录执行
conda create -n motionbricks python=3.10 -y
conda activate motionbricks
pip install -e ".[training,demo]"
python inference/cli/interactive_demo_g1.py
```

Windows 下默认打开中文单窗口界面，其他平台在不能嵌入 MuJoCo 窗口时回退为两个窗口。详见 [演示说明](docs/motionbricks/README.md) 和 [中文交互界面](docs/motionbricks/chinese_interface.md)。

仓库根目录的 `MotionBricks.exe` 是该参考演示的 Windows 启动器，固定读取根目录 `.venv` 中的环境；上面的 Conda 环境不会自动供 EXE 使用。它不包含 Python、模型和依赖，也不是 UE 插件启动器。

## 开发方向

第一阶段由 CMC / Mover 负责移动模拟，模型根据实际运动状态与未来轨迹生成角色姿态，再适配目标骨架：

```text
训练：UE 动画资产 → 采样与数据转换 → 模型训练 → 模型包

运行时目标：玩家 / AI 输入 → CMC 或 Mover → 运动状态与轨迹条件
                                                   ↓
                                      动画模型 → 骨架适配 → UE 姿态
```

运行时部分为开发目标。多人联机、统一人形模型、重定向与接触修正的职责和验收要求见 [第一阶段开发方案](unreal-script/AILocomotionSystem/LocomotionPlan.md)。

## 仓库与文档

已按职责重组。Python 导入名仍为 `motionbricks`，安装入口改为仓库根目录；数据、权重和检查点保留。目录与测试说明见 [仓库结构](docs/repository-layout.md)。

```text
data/               runtime/ · tools/ · prepared/（本地）
training/           pretrain/ · posttrain/ · common/ · models/ · evaluation/ · configs/ · runs/（本地）
model/motionbricks/ 网络、几何、动作表示与共享实现
model-weight/       base/motionbricks/ · 自定义发布产物
inference/          runtime/ · export/ · profiling/ · cli/ · demo/ · assets/
unreal-script/      AILocomotionSystem/ · python/
unreal-sample/      示例交付边界说明（当前无独立工程）
tests/              单元、训练、导出与目录回归测试
```

| 位置 | 用途 |
| --- | --- |
| [unreal-script](unreal-script/README.md) | UE 插件安装、动画导出、数据约定与训练说明 |
| [模型与参考演示说明](docs/motionbricks/README.md) | 上游模型技术说明与 G1 参考演示 |
| [动作表示](docs/motionbricks/motion_representation.md) | 骨架、Root Motion、姿态特征和坐标约定 |
| [接入自有数据集](docs/motionbricks/adding_your_own_dataset.md) | MotionBricks 通用数据集接入；UE 资产优先使用上面的插件说明 |
| [学习与项目历史](docs/project-background.md) | 源码阅读顺序、游戏动画裁剪范围与上游关系 |
| [launcher](launcher) | Windows 参考演示启动器源码 |

## 来源与许可

- **上游来源：** NVIDIA [GR00T-WholeBodyControl / MotionBricks](https://github.com/NVlabs/GR00T-WholeBodyControl/tree/main/motionbricks)。原作者、版权及论文信息予以保留；上游展示不能作为本项目新增 UE 功能的验证结果。
- **源代码：** 采用 Apache License 2.0，保留适用的版权与变更说明。
- **NVIDIA 预训练权重：** 单独适用 NVIDIA Open Model License，不能按源代码的 Apache 2.0 授权理解。
- **第三方资源与动画数据：** 依照各自授权使用；本仓库的代码许可证不授予外部动画资产、网格或数据集的使用权。

Licensed by NVIDIA Corporation under the NVIDIA Open Model License.

完整来源、许可文本入口、第三方声明和论文引用见 [引用与许可说明](引用与许可说明.md)、[NOTICE](NOTICE) 与 [LICENSE](LICENSE)。

---

本文件由 AIAnimationSystem 维护者基于上游 README 改写；2026-09-07 更新项目命名、使用入口、开发状态及来源声明。
