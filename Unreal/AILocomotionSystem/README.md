# AIAnimationSystem：UE 动画数据插件与训练

本目录属于 [AIAnimationSystem](../../README.md)，保留 `AILocomotionSystem` 插件集合目录与 `AILocomotionDataset` 插件标识。项目基于 NVIDIA MotionBricks 开发；来源、原论文和许可见 [引用与许可说明](../../引用与许可说明.md)。

> **当前状态：实验性实现，已完成真实资产导出、GPU 训练和留出集重建评估。** 本机 UEFN Mannequin 动画导出 1,728 段，预处理为 79 骨骼训练集；30 FPS 两轮 VQ-VAE 各训练 20,000 步，模型未扩容。已提供原生时间 HTML 对照和 FP32 推理包；UE 运行时推理、AnimGraph 输出及文字生成质量尚未验证。短姿态改善伴随部分常规动作退步，详见 [同预算实验记录](TrainingResults.md)。

本仓库以 `main` 作为主分支；插件与训练数据功能按实验性能力维护，未经独立动作质量评估不视为稳定能力。

当前实现 `AILocomotionDataset`：从项目中的 `UAnimSequence` 读取骨架和动画，将 UE Root 权威轨道与 Root 局部空间中的身体姿态分离，生成可用于训练自有 UE 骨架 Pose 模型的数据。模型推理与 AnimGraph 输出插件尚未实现。

[完整开发方案：多人联机、CMC / Mover、统一人形模型与训练路线](LocomotionPlan.md)。方案先概述后展开，明确第一阶段范围、模块职责、实施顺序和验收标准；规划能力尚未完整实现。

## 安装与动画导出

1. 把本目录复制到 UE 项目的 `Plugins/AILocomotionSystem/`。外层不放 `.uplugin`，里面的每个目录才是独立插件。
2. 为项目编译 Editor 目标，启用 **AI Locomotion Dataset**。当前接口依据本机 UE 5.8.2 源码实现。
3. 在项目设置中搜索 **AI Locomotion 动画数据**，设置 UE Root、骨盆、左右髋、脚踝、脚掌和双手。导出按源 AnimDataModel 的帧率与采样键求值，记录有理数帧率和逐帧时间戳；不再受旧 SampleRate 设置影响。默认名称适用于常见 Manny/Quinn 命名，但会按实际资产检查，不能仅凭“UE 骨架”认定兼容。
4. 在内容浏览器多选 `AnimSequence`，点击主菜单 **工具 → AI Locomotion：导出选中动画**。
5. 完整导出批次位于项目 `Saved/AILocomotionDataset/<唯一编号>/`，包含 `manifest.json`、每段动画的 JSON，以及批量模式下的 `batch_report.json`。

可用以下命令扫描指定目录下的全部 `AnimSequence`；失败项被记录到 `batch_report.json`，其余片段继续导出：

```powershell
D:/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe "D:/YourProject/YourProject.uproject" -AILocomotionExportPath=/Game/Characters/UEFN_Mannequin/Animations -unattended -nop4 -NoSplash
```

插件为纯 Editor 模块，不会进入打包游戏。它不修改、重定向或保存源动画资产。菜单导出在 Game Thread 上求值，显示进度并支持逐帧检查取消；期间编辑器处于模态任务状态。

## Python 环境

在仓库根目录创建 Python 3.12 虚拟环境，然后安装训练依赖：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r motionbricks/requirements-unreal-training.txt
uv pip install --python .venv/Scripts/python.exe --no-deps -e motionbricks
```

该依赖集用于数据处理和训练，不包含 MuJoCo 演示依赖。GPU 训练须安装与本机 CUDA 环境匹配的 PyTorch；通过 `--accelerator gpu` 显式请求 GPU。本机已用 CUDA 13.0 的 PyTorch 2.14 在 RTX 4070 Laptop GPU 上验证真实 UE 数据训练。

## 从导出数据训练

以下命令在仓库根目录执行。替换导出路径；输出目录必须尚不存在，避免覆盖已有数据或训练成果。

```powershell
.venv/Scripts/python.exe motionbricks/scripts/prepare_unreal_dataset.py --input "D:/YourProject/Saved/AILocomotionDataset/批次编号" --output motionbricks/unreal_data/walk --skip_invalid --short_clip_policy hold

.venv/Scripts/python.exe motionbricks/scripts/train_unreal.py --model vqvae --dataset motionbricks/unreal_data/walk --output motionbricks/unreal_runs/vqvae --max_steps 10000

.venv/Scripts/python.exe motionbricks/scripts/train_unreal.py --model pose --dataset motionbricks/unreal_data/walk --output motionbricks/unreal_runs/pose --vqvae motionbricks/unreal_runs/vqvae/checkpoints/final.ckpt --max_steps 10000

```

Schema v2 数据集声明 `pose_only_root_authoritative`：Root 世界运动由 CMC、Mover 或受控 Traversal Warp 提供，因此训练入口会拒绝 Root 模型。Pose 必须使用本数据集训练的 VQ-VAE，检查点绑定骨架及归一化统计量，不允许使用原 G1 权重。Pose 续训还会核对 VQ-VAE 文件哈希，避免换码本后误用原模型。旧 Schema v1 数据仍保留兼容读取能力，但不能冒充新的 Root/Pelvis 契约。

训练会保存 `config.yaml`、CSV 训练指标、周期检查点、`last.ckpt` 和正常完成时的 `final.ckpt`。使用 `--resume 路径` 恢复模型、优化器和训练步数；`--max_steps` 是恢复后总步数，学习率周期按本次总步数重新计算并从已恢复的步数继续。Pose 续训仍需提供原 VQ-VAE。只加载可信的本地检查点。

`--tiny --batch_size 1 --max_steps 2` 用于小网络冒烟验证。它不产生可部署的动作模型，不能与正常网络混用。`--short_clip_policy hold` 会保留原始短动作，并保持其末帧到最小训练窗口；不循环或拼接原始动态轨迹。旧训练入口仍把补齐帧作为目标；真实动画质量训练应使用下面的 `--native_quality` 入口，屏蔽补齐帧。训练步数不代表质量验收。

## 原生时间与质量训练

先盘点导出的 `fps`，每个原生帧率建立独立数据集；`--native_fps` 只筛选，不重采样。导出记录 `source_fps_numerator`、`source_fps_denominator`、`timestamps_seconds` 与源时长。预处理保存每段原始位置、旋转和时间戳到 `raw_*.npz`，用于不经过 FK 的参考对照。

```powershell
.venv/Scripts/python.exe motionbricks/scripts/prepare_unreal_dataset.py --input "D:/YourProject/Saved/AILocomotionDataset/批次编号" --output motionbricks/unreal_data/native30 --native_fps 30 --short_clip_policy hold --split
.venv/Scripts/python.exe motionbricks/scripts/train_unreal.py --model vqvae --dataset motionbricks/unreal_data/native30 --output motionbricks/unreal_runs/native30 --native_quality --max_steps 20000 --batch_size 4 --accelerator gpu
.venv/Scripts/python.exe motionbricks/scripts/evaluate_native_quality.py --dataset motionbricks/unreal_data/native30 --checkpoint motionbricks/unreal_runs/native30/checkpoints/final.ckpt --output motionbricks/unreal_runs/native30/test --split test
.venv/Scripts/python.exe motionbricks/scripts/export_native_gallery.py --input motionbricks/unreal_runs/native30/test/gallery.json --output "D:/YourOutput/动画训练效果.html"
```

`--split` 按去除末尾数字变体的资产名称家族，确定性分为约 80/10/10；小集合不保证三个划分都非空。统计量只使用训练分区的真实帧。缺少录制 ID，因此不能把名称分组称为录制级独立划分。

`--native_quality` 是 UE 专用 VQ 训练类：短片段的补齐仅用于卷积上下文，重建与运动损失使用真实帧掩码；类别采样权重为类别数量的平方根倒数；增加骨盆对齐 FK 位置、根轨迹、脚部、速度与参考接触约束。`--geometry_coeff 0` 可做几何项消融。码本和旧 Pose 检查点不能互换，文本标签尚未接入这一 VQ 训练入口。

`--pose_aware_sampling` 与 `--native_quality` 配合使用：真实长度按 16/32/64/更长分桶；短桶的窗口缩到批内最短真实长度的四倍数上界，最多补齐 3 帧。Ragdoll、Interactions、Traversal 类别在原类别权重上乘 1.5。它不改变网络参数、原生 FPS、数据划分或训练步数。`--checkpoint_every 5000` 可减少周期训练检查点的磁盘占用，不影响正常结束时保存最终权重。

`scripts/diagnose_unreal_capacity.py` 在验证集上比较离散码本与旁路连续隐变量的解码结果。旁路隐变量不一定属于解码器训练分布，因此该差值不是量化误差的独立因果分解。

`scripts/export_unreal_inference.py --checkpoint ... --output ...` 导出无优化器的 FP32 推理包，带可迁移的骨架、统计量与配置；同脚本中的 `load_package()` 重定位这些文件。`--decoder_only` 进一步移除编码器，只允许调用 `forward_decoder()` 接收兼容码本的 token；它不是独立文本生成系统。导出过程逐值验证权重，未作 FP16/INT8 或有损剪枝。PyTorch 推理包不等同于 ONNX、TensorRT 或 UE 部署插件。

评估恢复源初始朝向与平移后，与原始位置、旋转在同一采样时刻对照。分别报告世界位置、骨盆对齐姿态、根水平与高度误差，以及位置特征往返和固定骨长 FK 的表示误差。HTML 使用完整帧序列与原生时间戳，不依赖抽帧 GIF；可比较无关键帧、首帧与首尾关键帧条件。此结果是 VQ 编码重建和独立骨架预览，不替代文本生成、动作混合或 UE 蒙皮角色验收。

## 数据约定与支持边界

- Schema v2 原始导出：`root_frames` 保存组件空间 UE Root 审计轨道；`frames` 保存 Root 局部空间中的骨盆子树，单位为厘米、旋转为四元数 `xyzw`，JSON 明确标记 `unreal_root_relative_cm_xyzw`。
- 身体根节点默认 `pelvis`，保留它的全部子骨骼。UE Root 不进入训练骨架，也不由模型生成；它的世界移动在运行时由 CMC、Mover 或受控 Traversal Warp 提供。身体树外的 IK 辅助骨骼不参与训练，双手与双脚语义骨用于运行时 IK/warping 对接。
- 转换：`Motion(X,Y,Z) = UE(-Y,Z,X) / 100`。旋转执行基变换，并消除每根骨骼的参考旋转，使其符合现有 FK 算法。将来输出 UE 动画时必须恢复参考骨轴。
- 每个身体骨架有 J 根骨骼时，全局训练特征维数为 `12J + 6`，局部为 `12J + 5`，双表示为 `12J + 10`；不再固定为 G1 的 414 维。
- 每个数据集只能包含一致的骨架拓扑、参考姿态、语义映射和帧率。不同 `USkeleton` 路径但结构完全一致可以共用；结构不一致须分开处理。
- 拒绝叠加动画、非单位缩放、缺失或重复分配的语义骨骼、无效数值和每段超过配置上限的采样。左右髋与四个足部接触点必须分别对应不同骨骼。当前最大 512 根骨骼、18000 帧，且每段帧数乘骨骼数不能超过 250000。
- Unreal 的 `VB ` 虚拟骨骼不会进入训练骨架。实体骨骼的全局位置轨迹通过 `ric_data` 特征保留；生成结果若要回写 UE，仍需增加与位置轨迹一致的动画重建和质量验证。
- 预处理存储至少 65 帧；默认拒绝较短动作。指定 `--short_clip_policy hold` 时保留原始帧数并保持末帧；原生质量入口屏蔽补齐监督，启用长度分桶后可使用更短的实际训练窗口。不循环或拼接原始动态轨迹。
- 使用 UE Z=0 作为地面；足部接触由现有位置/速度阈值推导。不会把腾空动作强制平移到地面；数据需统一地面与单位。
- 原地动画没有前进位移，就无法仅凭该动画学习对应的前进根轨迹。需要带真实位移的 Root Motion 动画，或后续增加有明确规则的轨迹标注。
- 读取的是已被 Unreal 加载的动画资产；Python 不解析孤立的 `.uasset`。整个过程不需要手动导出 FBX。
- 原有 `interactive_demo_g1.py` 仍绑定 G1 控制器和 MuJoCo 映射，不能直接预览这些新 UE 骨架检查点。

失败或取消的导出批次可能保留诊断用的已写文件，但没有最终清单；预处理失败的输出也不会包含 `dataset.json`。重新执行时使用新输出目录。

## 验证

```powershell
.venv/Scripts/python.exe -m unittest discover -s motionbricks/tests -v
```

覆盖坐标与旋转基变换、虚拟骨骼剔除、实体骨骼平移保留、非法拓扑、四元数校验、混合骨架拒绝、统计量改变检查，以及 VQ-VAE/Root/Pose 三类模型的 CPU 小网络训练和续训、续训学习率周期、Pose 极低监督采样概率下的有限损失与梯度。测试数据为程序生成的骨骼动画；真实资产端到端结果见下一段。

2026-09-08 的早期验证完成 UE 5.8.2 插件打包、真实资产导出及 VQ-VAE/Pose 各 1,000 步训练；随后完成原生帧率修复与两轮 20,000 步 VQ 重建实验。最新数据划分、指标、资源实测与限制集中记录在 [TrainingResults.md](TrainingResults.md)。PR 自审修复后重新完成 Editor 模块编译与 DLL 链接，未追加正式模型训练。
