# AILocomotionSystem 插件集合

> **当前状态：实验性实现，真实资产端到端未验证。** 已通过 UE 5.8.2 编译与链接，以及程序生成动画夹具上的 CPU 小网络训练测试；尚未验证实际 UE 角色动画的插件导出、完整训练流程、GPU 训练或生成质量。因此目前不能确认该插件已可用于真实项目训练。

本仓库以 `codex/game-development-only` 作为主分支；插件与训练数据功能按实验性能力维护，未经真实资产验证不视为稳定能力。

当前实现 `AILocomotionDataset`：从项目中的 `UAnimSequence` 读取骨架和动画，生成可用于训练自有 UE 骨架模型的数据。模型推理与 AnimGraph 输出插件尚未实现。

[完整开发方案：多人联机、CMC / Mover、统一人形模型与训练路线](LocomotionPlan.md)。方案先概述后展开，明确第一阶段范围、模块职责、实施顺序和验收标准；规划能力尚未完整实现。

## 安装与动画导出

1. 把本目录复制到 UE 项目的 `Plugins/AILocomotionSystem/`。外层不放 `.uplugin`，里面的每个目录才是独立插件。
2. 为项目编译 Editor 目标，启用 **AI Locomotion Dataset**。当前接口依据本机 UE 5.8.2 源码实现。
3. 在项目设置中搜索 **AI Locomotion 动画数据**，设置骨盆、左右髋、脚踝、脚掌和采样率。默认名称适用于常见 Manny/Quinn 命名，但会按实际资产检查，不能仅凭“UE 骨架”认定兼容。
4. 在内容浏览器多选 `AnimSequence`，点击主菜单 **工具 → AI Locomotion：导出选中动画**。
5. 完整导出批次位于项目 `Saved/AILocomotionDataset/<唯一编号>/`，包含 `manifest.json` 和每段动画的 JSON。成功提示给出实际路径。

插件为纯 Editor 模块，不会进入打包游戏。它不修改、重定向或保存源动画资产。菜单导出在 Game Thread 上求值，显示进度并支持逐帧检查取消；期间编辑器处于模态任务状态。

## Python 环境

在仓库根目录创建 Python 3.12 虚拟环境，然后安装训练依赖：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r motionbricks/requirements-unreal-training.txt
uv pip install --python .venv/Scripts/python.exe --no-deps -e motionbricks
```

该依赖集用于数据处理和训练，不包含 MuJoCo 演示依赖。GPU 训练须安装与本机 CUDA 环境匹配的 PyTorch；通过 `--accelerator gpu` 显式请求 GPU，当前验证环境为 CPU。

## 从导出数据训练

以下命令在仓库根目录执行。替换导出路径；输出目录必须尚不存在，避免覆盖已有数据或训练成果。

```powershell
.venv/Scripts/python.exe motionbricks/scripts/prepare_unreal_dataset.py --input "D:/YourProject/Saved/AILocomotionDataset/批次编号" --output motionbricks/unreal_data/walk

.venv/Scripts/python.exe motionbricks/scripts/train_unreal.py --model vqvae --dataset motionbricks/unreal_data/walk --output motionbricks/unreal_runs/vqvae --max_steps 10000

.venv/Scripts/python.exe motionbricks/scripts/train_unreal.py --model pose --dataset motionbricks/unreal_data/walk --output motionbricks/unreal_runs/pose --vqvae motionbricks/unreal_runs/vqvae/checkpoints/final.ckpt --max_steps 10000

.venv/Scripts/python.exe motionbricks/scripts/train_unreal.py --model root --dataset motionbricks/unreal_data/walk --output motionbricks/unreal_runs/root --max_steps 10000
```

Root 不依赖 VQ-VAE，可独立训练。Pose 必须使用本数据集训练的 VQ-VAE，检查点绑定骨架及归一化统计量，不允许使用原 G1 权重。Pose 续训还会核对 VQ-VAE 文件哈希，避免换码本后误用原模型。

训练会保存 `config.yaml`、CSV 训练指标、周期检查点、`last.ckpt` 和正常完成时的 `final.ckpt`。使用 `--resume 路径` 恢复模型、优化器和训练步数；`--max_steps` 是恢复后总步数，学习率周期按本次总步数重新计算并从已恢复的步数继续。Pose 续训仍需提供原 VQ-VAE。只加载可信的本地检查点。

`--tiny --accelerator cpu --batch_size 1 --max_steps 2` 用于小网络冒烟验证。它不产生可用的动作模型，不能与正常网络混用。默认步数也不是质量承诺；当前训练入口记录训练损失，尚未提供独立验证集评估或动作质量评测。

## 数据约定与支持边界

- 原始导出：组件空间位置（厘米）、四元数 `xyzw`、参考姿态、父子索引和骨骼角色。JSON 明确标记 `unreal_component_cm_xyzw`。
- 身体根节点默认 `pelvis`，保留它的全部子骨骼。根骨骼及其他祖先的运动通过组件空间姿态合入骨盆轨迹；模型使用骨盆根节点，不单独训练 UE 的 `root` 轨道。身体树外的 IK 辅助骨骼不参与训练。
- 转换：`Motion(X,Y,Z) = UE(-Y,Z,X) / 100`。旋转执行基变换，并消除每根骨骼的参考旋转，使其符合现有 FK 算法。将来输出 UE 动画时必须恢复参考骨轴。
- 每个身体骨架有 J 根骨骼时，全局训练特征维数为 `12J + 6`，局部为 `12J + 5`，双表示为 `12J + 10`；不再固定为 G1 的 414 维。
- 每个数据集只能包含一致的骨架拓扑、参考姿态、语义映射和帧率。不同 `USkeleton` 路径但结构完全一致可以共用；结构不一致须分开处理。
- 拒绝叠加动画、非单位缩放、缺失或重复分配的语义骨骼、无效数值和每段超过配置上限的采样。左右髋与四个足部接触点必须分别对应不同骨骼。当前最大 512 根骨骼、18000 帧，且每段帧数乘骨骼数不能超过 250000。
- 当前 FK 表示不支持非根骨骼的独立动画平移。转换器检查参考骨长与姿态一致性，误差超过 5 毫米即拒绝，避免静默损坏数据。带 corrective/stretch 轨道的动画可能需要先烘焙或另行扩展模型表示。
- 训练片段至少 65 帧；默认 30 FPS 下建议至少 2.2 秒。不会自动重复或拼接短动画，因为这会制造速度不连续。
- 使用 UE Z=0 作为地面；足部接触由现有位置/速度阈值推导。不会把腾空动作强制平移到地面；数据需统一地面与单位。
- 原地动画没有前进位移，就无法仅凭该动画学习对应的前进根轨迹。需要带真实位移的 Root Motion 动画，或后续增加有明确规则的轨迹标注。
- 读取的是已被 Unreal 加载的动画资产；Python 不解析孤立的 `.uasset`。整个过程不需要手动导出 FBX。
- 原有 `interactive_demo_g1.py` 仍绑定 G1 控制器和 MuJoCo 映射，不能直接预览这些新 UE 骨架检查点。

失败或取消的导出批次可能保留诊断用的已写文件，但没有最终清单；预处理失败的输出也不会包含 `dataset.json`。重新执行时使用新输出目录。

## 验证

```powershell
.venv/Scripts/python.exe -m unittest discover -s motionbricks/tests -v
```

覆盖坐标与旋转基变换、非刚性平移拒绝、非法拓扑、四元数校验、混合骨架拒绝、统计量改变检查，以及 VQ-VAE/Root/Pose 三类模型的 CPU 小网络训练和续训、续训学习率周期、Pose 极低监督采样概率下的有限损失与梯度。测试数据为程序生成的刚性骨架动画，不等同于真实 Manny/Quinn 资产导出测试或动作质量验证。

2026-09-07：本机 UE 5.8.2 的 UHT、Editor 模块编译及 DLL 链接通过。标准 UAT BuildPlugin 在 AutomationTool 的缺失 NuGet 依赖处失败，后改用独立临时宿主项目和 UBT 编译成功；未生成正式分发包。实际角色资产的菜单操作、GPU 训练与生成效果尚未验证。
