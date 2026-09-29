# 无参考连续推理、脚部约束与 UE CMC Root 联合实验

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-25-closed-loop-optimization`；训练 / 推理 / UE 自动化 |
| 时间与时区 | 2026-09-25 +08:00；精确起止时间未记录 |
| 状态 | 实验完成；尚未达到 UE 玩家动画可用标准 |
| 执行者与来源 | Codex 在 AIAnimationSystem 本机工作区执行；数据及初始化权重为项目既有封版 |
| 前序记录 | [现有动作无参考推理诊断](2026-09-25-existing-motion-diagnostics.md)、[既有条件训练](../../training/conditioned_optimization_20260925.md) |

## 问题与实验设计

针对上一轮发现的生成历史回灌漂移、脚滑、以及来源未来 Root 不可在玩家运行时取得，分别做三组可比较实验：

1. 从相同的 `uniform12` 第 12 轮权重出发，以相同数据、种子、轮数和优化器微调 `real_history`、75% 概率使用模型自身生成历史的 `generated_history`，以及再加权重 `0.0005` 世界空间接触脚速损失的 `generated_contact`。输入没有未来姿态参考，但**训练和标准验证仍给来源未来 Root**。另试权重 `0.005` 和连续回灌两次再训练第三窗口的深度 2 版本。选择只看验证集，之后仅对选中权重跑一次冻结测试集。
2. 在 12 条固定验证片段上，对无修正、读取来源接触标签的上界、只看预测脚高度/速度的因果接触启发式做脚锁定及两骨骼位置 IK 对照。此实验用于否决或支持方案，不作为已集成运行时修正。
3. 在 UE 5.8.2 的真实 `ACharacter` / `UCharacterMovementComponent` 测试 World 内施加 30 Hz 脚本输入，记录 Walk/Run/Crouch 共 288 帧实际执行的位置、旋转、速度、胶囊高度和接受的蹲下状态。以此 Root 回放作为上界，并以当帧已接受 CMC 状态加当前输入保持 24 帧的简单预测作为因果代理，调用**UE 外的 Python 姿态模型**；单独构造 Walk 历史接 CMC 蹲下请求的负例。

主要指标：单窗口关节位置 RMSE（cm）、来源启发式接触帧对上的脚/趾速度（m/s）、12 条连续 72 帧的第三个 24 帧块 RMSE、CMC Root 第 24 帧末误差（cm），以及直接观看 72 帧骨架视频。对照均无未来姿态参考。真实玩家控制、蒙皮、地形、碰撞脚部与网络校正不在此次通过范围。

## 代码、环境、数据和复现

- HEAD：`e07aad29773bf24dcadd98e36271d3af1894e7fe`。实验在未提交工作区执行；相关改动在本记录、`assets/2026-09-25-closed-loop-optimization/`、[UE CMC 测试](../../unreal-script/AIAnimation/Source/AIAnimation/Private/AIAnimationCMCRootCaptureTests.cpp)及前序诊断脚本。原始封版数据、分区、初始化权重未改。
- 来源清单 SHA-256 `9a6c10fa2cd906c47f7f137cf5a83361e86fbbb40d2a7182d8e87c631145483a`；封版契约 SHA-256 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`；79 骨骼、30 FPS。初始化 `uniform12` SHA-256 `28662ffd1855ab18fc8091f866252d1800bbd2a2595222b907009891f0eb3930`。
- 单次回灌训练：训练分区 Walk/Run/Crouch 中至少 72 帧的 938 段；两次回灌：至少 96 帧的 792 段。原分区隔离，读取每段原始文件时检查其 SHA-256。验证固定 142 段中心窗口、12 段连续输出；冻结测试 176 段中心窗口。并未针对这些结果重新人工验收全部资产。
- 10 epochs、batch 8、AdamW `3e-5`、weight decay `0.01`、seed `20260925`；模型每次从相同初始权重重启。接触损失对预测姿态按来源 Root 恢复世界脚位；训练使用来源派生接触位和来源未来 Root。生成历史时将 6D 旋转正交化后回灌，与当前推理路径相符。配置快照：[一次回灌](assets/2026-09-25-closed-loop-optimization/train_one_step_config.json)、[两次回灌](assets/2026-09-25-closed-loop-optimization/train_two_step_config.json)。
- 本机 RTX 4070 Laptop GPU；Python 3.12.12、PyTorch 2.14.0+cu130、NumPy 2.5.3、SciPy 1.18.1；UE 5.8.2。未启用远程 GPU。权重和全量 NPZ 输出仅在本机 `E:\AIAnimationSystemData\training_runs\` 与工作区 `output/`；下方小型指标、CSV、视频随记录保存。

主要复现入口（在该 worktree 根目录，`PYTHONPATH` 为项目根目录；各 `--output` 要求新目录）：

```powershell
$env:PYTHONPATH=(Get-Location).Path
$py='D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe'
$assets='docs/experiments/assets/2026-09-25-closed-loop-optimization'
& $py "$assets/train_rollout_ablation.py" --output 'E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02' --epochs 10 --batch-size 8 --lr 3e-5 --seed 20260925 --contact-weight 0.0005
& $py "$assets/train_two_step_ablation.py" --output 'E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_two_step_ablation01' --epochs 10 --batch-size 8 --lr 3e-5 --seed 20260925 --contact-weight 0.0005
& $py 'docs/experiments/assets/2026-09-25-existing-motion-diagnostics/evaluate_existing_motion.py' --output 'output/closed_loop_eval_20260925_run02' --checkpoint 'uniform12=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_uniform12\epoch_012.pt' --checkpoint 'real_history10=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02\real_history\epoch_010.pt' --checkpoint 'generated_history10=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02\generated_history\epoch_010.pt' --checkpoint 'generated_contact10=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02\generated_contact\epoch_010.pt'
& $py "$assets/evaluate_foot_lock.py" --output 'output/foot_lock_20260925_run02'
& 'D:\UE_5.8\Engine\Build\BatchFiles\Build.bat' UnrealEditor Win64 Development '-Project=D:\AILocomotonSystem\GR00T-WholeBodyControl-p0-review\output\ue_cmc_host\Host.uproject' -WaitMutex -NoHotReloadFromIDE
$env:AIANIMATION_CMC_TRACE_PATH=(Join-Path (Get-Location) 'output/cmc_root_capture_20260925_v2.csv')
& 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' 'output/ue_cmc_host/Host.uproject' '-ExecCmds=Automation RunTests AIAnimation.Lab.CMCRootCapture' '-TestExit=Automation Test Queue Empty' -unattended -nop4 -nullrhi
& $py "$assets/evaluate_cmc_root.py" --trace 'output/cmc_root_capture_20260925_v2.csv' --output 'output/cmc_ground_root_inference_20260925_run03' --checkpoint 'uniform12=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_uniform12\epoch_012.pt' --checkpoint 'generated_contact10=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02\generated_contact\epoch_010.pt'
```

宿主项目 `output/ue_cmc_host/Host.uproject` 是本机临时最小项目，其 `Plugins/AIAnimation` 指向当前工作区插件；无需将生成的 UE 项目或构建缓存入库。冻结测试采用原 `training/evaluation/evaluate_conditioned_quality.py` 的 `test / middle_window_per_clip` 口径。渲染入口和参数可见 [来源 Root 视频脚本](assets/2026-09-25-closed-loop-optimization/render_ablation_comparisons.py)及 [CMC Root 视频脚本](assets/2026-09-25-closed-loop-optimization/render_cmc_comparisons.py)。

## 结果与证据

### 训练改动：平均改善，但 Walk 长序列存在反例

| 测试 | `uniform12` | 选中 `generated_contact10` | 口径与证据 |
| --- | ---: | ---: | --- |
| 冻结测试无参考姿态 RMSE | 9.766 cm | **9.012 cm** | 176 段各一中心窗口，来源未来 Root；[选中权重测试](assets/2026-09-25-closed-loop-optimization/frozen_test_selected.json)及既有基线记录 |
| 冻结测试派生接触脚速 | 0.731 m/s | **0.637 m/s** | 同上；来源动作约 **0.049 m/s**，仍有显著脚滑 |
| 验证 Walk 第三块 RMSE / 脚速 | 19.13 cm / 1.14 m/s | **19.49 cm / 0.97 m/s** | 4 段；姿态稍退步 |
| 验证 Run 第三块 RMSE / 脚速 | 23.67 cm / 2.58 m/s | **20.41 cm / 2.40 m/s** | 4 段 |
| 验证 Crouch 第三块 RMSE / 脚速 | 23.91 cm / 1.65 m/s | **19.69 cm / 1.30 m/s** | 4 段 |

完整三臂对照及 142 段单窗结果在[验证汇总](assets/2026-09-25-closed-loop-optimization/validation_ablation_summary.json)。`real_history` 单独微调没有稳定改善连续回灌；使用生成历史主要改善 Run/Crouch。将接触权重提高到 `0.005` 后 Crouch 单窗脚速从低权重的 0.59 增至 0.64 m/s，姿态误差也从 8.79 增至 9.02 cm，见[强接触对照](assets/2026-09-25-closed-loop-optimization/validation_contact005_summary.json)。两次回灌版本的 Run 长序列更好，但 Walk/Crouch 和中心窗口并非全优，见[深度 2 对照](assets/2026-09-25-closed-loop-optimization/validation_two_step_summary.json)。因此选一次回灌、轻量接触的第 10 轮做冻结测试；**未用测试集继续调参**。选中权重 SHA-256 `d5e1176444238c243d8836bd2b8139485a2ec8e607ea4a5cdb7fb5a14a69ee5a`，仅本机 `E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02\generated_contact\epoch_010.pt` 可用。

可播放 72 帧骨架对照：[Walk](assets/2026-09-25-closed-loop-optimization/media/walk_1306_baseline_vs_optimized.mp4)、[Run](assets/2026-09-25-closed-loop-optimization/media/run_983_baseline_vs_optimized.mp4)、[Crouch](assets/2026-09-25-closed-loop-optimization/media/crouch_49_baseline_vs_optimized.mp4)；画面从左至右为来源、旧权重、新权重，均无参考且给相同来源未来 Root。Walk 样例末帧目测不如旧模型，Run 改善更明显，Crouch 略有改善；三条样例不能代替总体结论。[视频清单](assets/2026-09-25-closed-loop-optimization/media/manifest.json)含哈希。

### 脚锁定：当前因果接触识别不够可靠

在固定 12 段里，来源标签驱动的理想脚锁定可把**踝关节**标记接触期的速度压至接近 0；它需要推理时拿不到的来源接触标签。仅用预测高度和速度的启发式，接触判定相对来源标签的平均 precision 为 Walk **0.42**、Run **0.23**、Crouch **0.22**；Walk 和 Crouch 的姿态 RMSE 分别从 14.91→15.26、16.56→16.84 cm。此修正只处理骨骼**位置**，没有同步修复旋转/蒙皮，也不包含真实地面查询。结果见[逐条脚锁定 CSV](assets/2026-09-25-closed-loop-optimization/foot_lock_results.csv)。因此这版启发式**不采用为 UE 运行时修正**；脚速下降不能以错误接触判定和姿态损坏为代价。

### 实际 CMC Root：找出蹲下时 48 cm 的坐标约定错误

UE 自动化测试编译并运行成功，目标测试 `AIAnimation.Lab.CMCRootCapture` 返回 `Result={Success}`。导出的[288 帧 CMC CSV](assets/2026-09-25-closed-loop-optimization/ue_cmc_trace.csv) SHA-256 为 `9180776b198a0c1a5d03508fb9e69a914086f13da251bb7a5afe12e72df26fb6`；三段均处于 Walking。蹲下接受时胶囊半高从 88→40 cm，胶囊中心 Z 从约 90.15→42.15 cm；直接将 `GetActorLocation()` 当作数据 Root 会凭空引入约 **48 cm** 的竖向跳变，使脚落到地面下约 35–36 cm。此次离线适配改为 `ActorLocation.Z - 当前胶囊半高`，平地脚回到约 +12–13 cm，并消除这个虚假的 Root 阶跃。该约定是**本项目数据与平地 CMC 的对齐规则**，斜坡/移动平台/不同胶囊配置尚需验证。

即使坐标对齐，简单的“当前输入保持 24 帧”计划在 Run 转弯的第二块末仍偏离真实 CMC **39.92 cm**，第三块 **26.51 cm**；Walk 对应 3.51 / 1.97 cm，Crouch 1.50 / 0.39 cm。该预测只是离线因果代理，不能冒充真正的未来 CMC 预测或玩家输入录制。数据与两模型推理指标见[CMC Ground Root 汇总](assets/2026-09-25-closed-loop-optimization/cmc_ground_root_summary.json)。

可观看 CMC Root 条件下的 [Walk](assets/2026-09-25-closed-loop-optimization/cmc_contract_media/walk_cmc_root_comparison.mp4)、[Run](assets/2026-09-25-closed-loop-optimization/cmc_contract_media/run_cmc_root_comparison.mp4)、[Crouch](assets/2026-09-25-closed-loop-optimization/cmc_contract_media/crouch_cmc_root_comparison.mp4)、[站立历史接蹲下请求](assets/2026-09-25-closed-loop-optimization/cmc_contract_media/stand_to_crouch_cmc_root_comparison.mp4)。画面是 Python 模型骨架叠加真实 CMC Ground Root / 因果代理轨迹；本次实验的模型未在 UE 中运行或蒙皮，后续[UE 内 NNE 蒙皮验证](2026-09-25-ue-skinned-inference.md)补上了这一步。[修正后清单](assets/2026-09-25-closed-loop-optimization/cmc_contract_media/manifest.json)含视频哈希。初版 `cmc_ground_media` 的横向轴映射符号与封版数据契约相反，已由 `run03` 及本组视频取代；旧视频不得用于判断左右方向。

站蹲负例中，CMC 已接受蹲下 48 帧，但旧/新权重的局部骨盆仍处于约 0.88–0.91 m 的站姿范围；当前 v1 模型没有玩家 Stand/Crouch 状态输入，也缺少未来站蹲切换训练样本。修复 Root 坐标不会自动让模型蹲下。此负例直接否定“现在可以由模型完整承担蹲下/起立”的说法。

## 结论、限制与下一步

- **直接测得：**冻结测试集无参考、来源 Root 条件下，选中权重使姿态误差约降低 7.7%，派生脚速约降低 12.8%；仍远高于来源脚速。Run/Crouch 的固定连续样例改善，Walk 第三块姿态略退步。UE CMC 测试得到真实胶囊轨迹，验证了蹲下时必须使用胶囊底部来对齐本项目地面 Root。因果脚接触启发式和站蹲响应目前不合格。
- **工程判断：**可以将新权重作为后续无参考实验候选，不能宣称脚滑已解决或能驱动完整玩家动画。优先建立 UE 中可在线取得的未来 Root 规划与统一坐标契约，再建立明确的 Stand/Crouch 请求/接受状态、切换片段和模型条件；脚接触应由可靠的运行时地面/足部状态驱动，并验证完整骨骼旋转和蒙皮。
- **本实验未验证：**真实手柄/键鼠输入、UE 内模型推理与蒙皮、网络预测与校正、斜坡/台阶/移动平台、跨片段过渡及真正的起立样本。后续已完成隔离的 [UE NNE 蒙皮渲染](2026-09-25-ue-skinned-inference.md)，但仍不是在线玩家控制闭环。12 条连续片段不能证明所有动作泛化。接触标签来自来源姿态的启发式，脚速不是游戏物理接触误差。
- **归属边界：**本次是项目现有模型和数据上的衍生微调、评估及 CMC 测试；上游已有模型/资产与本次结果不混称。后续如进入正式 UE 集成，应另建可复现的端到端实验，保留失败样例。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-25 | 首次记录三项实验、选中权重、失败样例与视频 | 配置、验证及冻结测试 JSON、UE CSV、MP4 清单 |
| 2026-09-25 | 修正 UE 横向轴至数据契约 `data X = -UE Y`，重跑 CMC 对照并重渲视频；初版视频标为失效 | `run03` 汇总、`cmc_contract_media` 清单；Root 误差数值未变 |
