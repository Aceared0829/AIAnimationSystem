# MotionBricks：基于模块化潜变量生成模型与智能基元的可扩展实时动作系统

> **游戏动画分支：** 本分支已经移除机器人控制、硬件部署和遥操作组件。G1 骨架仅作为已发布 MotionBricks 检查点所需的参考角色骨架保留。

<p align="center">
  <a href="https://nvlabs.github.io/motionbricks"><img src="https://img.shields.io/badge/项目主页-访问-blue" alt="项目主页"></a>
  <a href="docs/motion_representation.md"><img src="https://img.shields.io/badge/文档-在线-green.svg" alt="文档"></a>
</p>

<p align="center">
  <img src="assets/teaser_motion_bricks_three_rows.jpg" alt="MotionBricks 效果预览" width="100%">
</p>

MotionBricks 是一个面向交互式角色动画的实时生成框架。它将大规模潜变量骨干网络与直观的“智能基元”结合起来，能够以每秒 15,000 帧的速度完成高质量零样本动作合成，并使复杂动作能够像积木一样自由组合。

## 目录

- [新闻与路线图](#新闻与路线图)
- [效果展示](#效果展示)
- [环境配置](#环境配置)
- [交互演示快速开始](#交互演示快速开始)
- [训练](#训练)
- [动作表示与自定义数据集](#动作表示与自定义数据集)
- [相关工作](#相关工作)
- [项目结构](#项目结构)
- [已知问题](#已知问题)
- [论文引用](#论文引用)
- [许可证](#许可证)
- [联系方式](#联系方式)

## 新闻与路线图

### 新闻

- **2026-04-27**：首次公开发布，包含交互演示、预训练检查点（VQ-VAE、姿态模型、根节点模型）、合成数据训练代码、动作表示文档和 GIF 展示。

### 路线图

- [ ] 支持更多角色骨架，并提供游戏引擎导出器和运行时适配器。

## 效果展示

完整的无剪辑演示和对比视频请参阅[项目主页](https://nvlabs.github.io/motionbricks)。以下为静音短 GIF，每段约 10 秒。

### 效果预览

![动画效果预览](assets/gifs/teaser_animation.gif)

### 智能移动——单一风格

| 僵尸 | 腿部受伤 |
| :---: | :---: |
| ![僵尸](assets/gifs/loco_zombie.gif) | ![腿部受伤](assets/gifs/loco_injured_leg.gif) |
| **躯干受伤** | **跳步** |
| ![躯干受伤](assets/gifs/loco_injured_torso.gif) | ![跳步](assets/gifs/loco_skipping.gif) |
| **侧向移动** | **蹲伏侧移** |
| ![侧向移动](assets/gifs/loco_strafing.gif) | ![蹲伏侧移](assets/gifs/loco_crouch_strafing.gif) |

### 智能移动——混合风格

| 自由风格 | 待机、行走、慢跑、奔跑 |
| :---: | :---: |
| ![自由风格](assets/gifs/loco_freestyle.gif) | ![待机、行走、慢跑和奔跑](assets/gifs/loco_idle_walk_jog_run.gif) |

### 智能物体交互

| 拾取长剑 | 跌落 |
| :---: | :---: |
| ![拾取长剑](assets/gifs/obj_pickup_sword.gif) | ![跌落](assets/gifs/obj_falling.gif) |
| **跃过长凳** | **坐下** |
| ![跃过长凳](assets/gifs/obj_jump_bench.gif) | ![坐下](assets/gifs/obj_sitting.gif) |
| **交互式编排** | |
| ![交互式编排](assets/gifs/obj_interactive_authoring.gif) | |

## 环境配置

**要求：** Python 3.10 或更高版本、支持 CUDA 的显卡，以及 [Git LFS](https://git-lfs.com/)。

### 克隆仓库

MotionBricks 位于 `motionbricks/` 目录。预训练检查点、网格资源和展示 GIF 由 Git LFS 管理，因此请先安装并启用 Git LFS：

```bash
git lfs install
```

普通克隆不会自动下载约 2.2 GiB 的 MotionBricks 预训练检查点。如果只需要源代码，例如准备使用自己的数据训练，可以直接克隆：

```bash
git clone https://github.com/Aceared0829/GR00T-WholeBodyControl.git
cd GR00T-WholeBodyControl/motionbricks
```

如需运行交互演示，请在仓库根目录显式拉取检查点和 G1 参考角色网格：

```bash
git clone https://github.com/Aceared0829/GR00T-WholeBodyControl.git
cd GR00T-WholeBodyControl
git lfs pull --include="motionbricks/out/**" --exclude=""
git lfs pull --include="motionbricks/assets/skeletons/g1/meshes/**" --exclude=""  # 交互演示需要
cd motionbricks
```

拉取后检查文件大小，确认获得的不是很小的 Git LFS 指针文件：

```bash
ls -lh out/G1-clip.ckpt                                     # 约 7.5 MB
ls -lh out/motionbricks_vqvae/version_1/checkpoints/*.ckpt  # 约 273 MB
ls -lh out/motionbricks_pose/version_1/checkpoints/*.ckpt   # 约 1.6 GB
ls -lh out/motionbricks_root/version_1/checkpoints/*.ckpt   # 约 391 MB
```

如果文件只有约 1 KB，说明它是 LFS 指针。请回到仓库根目录运行 `git lfs pull --include="motionbricks/out/**" --exclude=""` 下载真实检查点。

### 安装依赖

```bash
# 创建环境
conda create -n motionbricks python=3.10 -y
conda activate motionbricks

# 安装依赖
pip install -e .

# 仅 Linux：用于键盘输入和 MuJoCo 按键捕获规避方案
pip install pynput python-xlib
```

## 交互演示快速开始

```bash
DISPLAY=:1 python scripts/interactive_demo_g1.py
```

程序会打开 MuJoCo 查看器并加载 G1 参考角色。使用键盘实时控制角色；按住鼠标左键并拖动可以改变相机观察方向。

默认同时打开 **MotionBricks 中文控制台**，并隐藏 MuJoCo 原生查看器中无法配置语言的英文侧栏。中文控制台提供运行/暂停、重置角色、退出演示、相机预设、接触点/关节/半透明显示开关和完整按键说明。若需要恢复 MuJoCo 原生英文侧栏，可运行：

```bash
python scripts/interactive_demo_g1.py --chinese_ui 0
```

<p align="center">
  <img src="assets/gifs/interactive_demo.gif" alt="交互演示录屏" width="480">
</p>

### 移动控制

| 按键 | 动作 |
|---|---|
| `W` | 向前移动 |
| `A` | 向左移动 |
| `S` | 向后移动 |
| `D` | 向右移动 |

移动方向以相机为参照。在 MuJoCo 查看器中按住鼠标右键并拖动可以旋转相机。

### 动作风格

| 按键 | 风格 |
|---|---|
| `V` | 慢走 |
| `Z` | 手部支撑爬行 |
| `X` | 拳击式行走 |
| `B` | 肘部支撑爬行 |
| `R` | 潜行 |
| `T` | 受伤行走 |
| `C` | 蹲伏潜行 |
| `E` | 快乐舞步 |
| `F` | 僵尸行走 |
| `G` | 持枪行走 |
| `Q` | 惊恐行走 |

注意：爬行模式（`Z` 手部支撑爬行和 `B` 肘部支撑爬行）目前不支持纯侧向移动。

不按风格键时，默认移动方式为：没有按下移动键时**待机**，按下 WASD 时**行走**。

## 训练

项目为三个模型组件分别提供了训练脚本。脚本默认使用合成数据，并从 `out/` 中保存的检查点目录加载模型配置。完整动作数据集可在 <https://bones.studio/datasets> 获取。

```bash
# 训练 VQ-VAE（动作分词器）
python scripts/train_vqvae.py

# 训练姿态模型（需要预训练 VQ-VAE 检查点）
python scripts/train_pose.py

# 训练根节点模型（不需要 VQ-VAE）
python scripts/train_root.py
```

### 数据集

预训练检查点所用的数据集可以从 <https://bones.studio/datasets> 下载。当前所有训练脚本默认使用**合成数据**，实现位于 `motionbricks/data/synthetic_dataset.py`，因此无需真实数据集也能端到端验证训练流程。

## 动作表示与自定义数据集

动作特征表示、骨骼系统、坐标约定、归一化和特征计算流程详见[动作表示](docs/motion_representation.md)。

如何使用自己的动作数据训练 MotionBricks，以及如何适配新的角色骨架，详见[添加自定义数据集](docs/adding_your_own_dataset.md)。

## 相关工作

**Kimodo**：专注离线动作生成的同系列项目，与 MotionBricks 的实时运行时互补。

[项目主页](https://research.nvidia.com/labs/sil/projects/kimodo/) · [GitHub](https://github.com/nv-tlabs/kimodo)

<p align="center">
  <img src="assets/gifs/kimodo_teaser.gif" alt="Kimodo 效果预览" width="480">
</p>

**BONES-SEED 数据集**：MotionBricks 使用的训练语料，包含由真人演员采集的 35 万段生产级动作捕捉片段。

[数据集页面](https://huggingface.co/datasets/bones-studio/seed)

<p align="center">
  <img src="assets/gifs/bones_seed_teaser.gif" alt="BONES-SEED 效果预览" width="480">
</p>

**SOMA Retargeter**：基于 Newton 的重定向求解器，将 SOMA 捕捉数据重定向到 G1 参考骨架，用于生成 MotionBricks 训练数据。

[GitHub](https://github.com/NVIDIA/soma-retargeter)

<p align="center">
  <img src="assets/gifs/soma_retargeter_teaser.gif" alt="SOMA Retargeter 效果预览" width="480">
</p>

## 项目结构

```text
motionbricks/
  assets/skeletons/g1/     # MuJoCo XML 和 STL 网格
  motionbricks/            # Python 包
  scripts/
    interactive_demo_g1.py # 交互演示
    train_vqvae.py         # VQ-VAE 训练
    train_pose.py          # 姿态模型训练
    train_root.py          # 根节点模型训练
  out/                     # 预训练检查点（Git LFS）
    G1-clip.ckpt
    motionbricks_vqvae/
    motionbricks_pose/
    motionbricks_root/
  setup.py
```

## 已知问题

- **仅 Linux/X11：** 键盘按键捕获规避方案依赖 X11（`python-xlib`）。在 Wayland、macOS 或 Windows 上，部分 MuJoCo 快捷键可能与控制键冲突。临时解决方法是让**终端保持焦点**，而不是 MuJoCo 窗口。
- **`PYTORCH_JIT=0` 会禁用按键捕获：** 使用 `PYTORCH_JIT=0` 运行会干扰 X11 按键捕获方案。如必须使用该设置，请让终端保持焦点。
- Linux/macOS 的键盘输入需要 `pynput`；Windows 使用 `keyboard` 包。

## 论文引用

如果在研究中使用 MotionBricks，请引用：

```bibtex
@misc{wang2026motionbricksscalablerealtimemotions,
      title={MotionBricks: Scalable Real-Time Motions with Modular Latent Generative Model and Smart Primitives},
      author={Tingwu Wang and Olivier Dionne and Michael De Ruyter and David Minor and Davis Rempe and Kaifeng Zhao and Mathis Petrovich and Ye Yuan and Chenran Li and Zhengyi Luo and Brian Robison and Xavier Blackwell and Bernardo Antoniazzi and Xue Bin Peng and Yuke Zhu and Simon Yuen},
      year={2026},
      eprint={2604.24833},
      archivePrefix={arXiv},
      primaryClass={cs.RO},
      url={https://arxiv.org/abs/2604.24833},
}
```

## 许可证

源代码采用 **Apache 2.0** 许可证。预训练模型权重采用 **NVIDIA Open Model License**，在遵守署名和可信人工智能要求的前提下允许商业使用。法律效力以仓库根目录中的英文 `LICENSE` 原文为准，中文解释见[引用与许可说明](../引用与许可说明.md)。

## 联系方式

问题和反馈请发送至 **`gear-wbc@nvidia.com`**。
