# 现有动作无参考推理：脚部、接缝与 Root 条件诊断

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-25-existing-motion-diagnostics`；离线评估 / 推理 |
| 开始、结束时间与时区 | 2026-09-25 +08:00；20:22 为运行完成后记录时刻，精确起止未记录 |
| 状态 | 完成；数值诊断，未进行 UE 蒙皮验收 |
| 执行者与来源 | Codex 在 AIAnimationSystem 本机工作区执行；两份权重与数据均为项目既有封版 |
| 前序记录 | [P0 数据审计](2026-09-25-p0-stance-data-audit.md)、[条件训练优化](../../training/conditioned_optimization_20260925.md) |

## 问题与方案

研究问题：现有无未来姿态参考的条件模型，在 Walk/Run/Crouch 中脚滑和接缝有多严重？已生成姿态回灌历史后是否累积误差？原动作未来 Root 换成只看过去的简单 Root 计划后，问题来自哪里？

- 对照权重：同一封版数据、12 轮的 `uniform12` 与 `hybrid12`。本次只加载权重推理，**没有训练**。
- 验证集各片段取一个中心窗口：Walk 50、Run 42、Crouch 50，共 142 段。无参考，输入历史 24 帧与原动作未来 Root 24 帧，复用原评估器的位置/脚速公式；额外计算历史末帧到首个预测帧的世界空间骨骼跳变。
- 同一 142 段另以**过去 6 个 Root 增量的平均位移/局部偏航**外推未来 24 帧。它不用未来真值，也没有玩家命令或 CMC，目的是量化最简单的因果 Root 方案的误差，以及姿态模型对 Root 条件变化的响应。Root 改变时与原动作姿态真值的距离不是公平的生成质量指标，因此只报告 Root 误差和两种条件下的姿态差异。
- 固定 12 条验证片段（Walk/Run/Crouch 各 4 条，覆盖 full、pivot、stop、spin）连续生成 72 帧；比较每 24 帧和每 4 帧重新规划。首轮输入为真实历史，之后实际显示的预测姿态和旋转回灌历史；同帧另用真实历史做 teacher-forced 对照。两组持续使用原动作未来 Root，不涉及跨片段切换。
- 脚速只在源动作派生的四个脚/趾接触标签**连续两帧均成立**时统计：先求每段有效帧对平均，再按片段等权平均。标签是启发式，不能证明 UE 物理接触。

## 代码、环境与数据

- 仓库 HEAD：`e07aad29773bf24dcadd98e36271d3af1894e7fe`。执行时工作区 `dirty`：已有未提交的 `docs/player-state-conditioned-animation-plan.md` 修改和 `output/p0_20260925/`；本实验新增本记录、索引、[评估脚本](assets/2026-09-25-existing-motion-diagnostics/evaluate_existing_motion.py)、[绘图脚本](assets/2026-09-25-existing-motion-diagnostics/plot_foot_contact_examples.py) 与小型证据。本实验未修改来源 NPZ、分区、权重或封版契约。
- 设备与依赖：本机 NVIDIA GeForce RTX 4070 Laptop GPU；Python 3.12.12、PyTorch 2.14.0+cu130、NumPy 2.5.3、SciPy 1.18.1。未使用远程 GPU。
- 来源清单 SHA-256：`9a6c10fa2cd906c47f7f137cf5a83361e86fbbb40d2a7182d8e87c631145483a`；封版契约 SHA-256：`9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`；79 骨骼、30 FPS、Root 与身体姿态独立。训练/验证/测试窗口 26,861/4,052/3,820；本轮只读验证集。
- `uniform12` 检查点 SHA-256：`28662ffd1855ab18fc8091f866252d1800bbd2a2595222b907009891f0eb3930`；`hybrid12`：`fc5cb84b737d0bb0e9e87fd2bad423388cb52aa03822fe657627a9f9b4fcd436`。两份权重仅在本机 `E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_{uniform12,hybrid12}` 可用。
- 复现命令（项目根目录 PowerShell；输出目录须不存在）：

```powershell
$env:PYTHONPATH=(Get-Location).Path
& 'D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe' docs\experiments\assets\2026-09-25-existing-motion-diagnostics\evaluate_existing_motion.py --output output\existing_motion_diagnostics_20260925_run03
& 'D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe' docs\experiments\assets\2026-09-25-existing-motion-diagnostics\plot_foot_contact_examples.py
```

第一次脚本运行 `run01` 产出单窗与 24 帧重规划；`run02` 增加 teacher-forced 对照；`run03` 增加 4 帧重规划，为本记录采用的完整结果。旧输出未覆盖。最终小型原始证据复制至 [assets/2026-09-25-existing-motion-diagnostics](assets/2026-09-25-existing-motion-diagnostics)：[汇总 JSON](assets/2026-09-25-existing-motion-diagnostics/summary.json)、[142 段逐条 CSV](assets/2026-09-25-existing-motion-diagnostics/center_validation.csv)、[24 帧重规划 CSV](assets/2026-09-25-existing-motion-diagnostics/rollouts.csv)、[4 帧重规划 CSV](assets/2026-09-25-existing-motion-diagnostics/rollouts_4frame.csv)、[接触脚速示例图](assets/2026-09-25-existing-motion-diagnostics/foot_contact_examples.png)。`summary.json` SHA-256：`264a18b2d1d235b1d7a84e210dce4d2925d46ff2941ee7ba9a347c1c2e62df2d`。本机完整运行输出在 `output/existing_motion_diagnostics_20260925_run03/`。

## 结果与证据

### 可播放的实际推理对照

2026-09-25 再次从 E 盘读取同一封版数据和 `hybrid12` 权重，对 Walk 1306、Run 983、Crouch 49 各生成 72 帧骨架动画：[Walk 视频](assets/2026-09-25-existing-motion-diagnostics/walk_1306_source_teacher_closed.mp4)、[Run 视频](assets/2026-09-25-existing-motion-diagnostics/run_983_source_teacher_closed.mp4)、[Crouch 视频](assets/2026-09-25-existing-motion-diagnostics/crouch_49_source_teacher_closed.mp4)。每个画面从左到右为源动作、每 24 帧更新真实历史的模型输出、生成历史回灌的模型输出。三栏使用相同的来源未来 Root，均无未来姿态参考；只有第一轮使用相同的 24 帧真实历史。绿色和橙色短线是左右脚最近 10 帧的世界轨迹，圆圈使用源动作派生的接触标签。源 30 FPS，视频按 15 FPS 慢放，全长 4.8 秒。这里展示的是**重新运行模型产生的骨骼位置**，不是 UE 蒙皮、IK 或玩家控制器的运行画面。

[渲染脚本](assets/2026-09-25-existing-motion-diagnostics/render_model_comparisons.py)与[视频清单及哈希](assets/2026-09-25-existing-motion-diagnostics/render_manifest.json)记录了输入、权重和文件指纹。完整逐帧 PNG 和预测数组保存在本机 `output/existing_motion_visual_20260925_run01/`。对应静帧：[Walk](assets/2026-09-25-existing-motion-diagnostics/walk_1306_poster.png)、[Run](assets/2026-09-25-existing-motion-diagnostics/run_983_poster.png)、[Crouch](assets/2026-09-25-existing-motion-diagnostics/crouch_49_poster.png)。这三条是便于观察的样例，不能替代下方的 142 段整体统计。

为排查 E 盘故障，本次检查了封版目录、来源数据目录、37 MB 的 `hybrid12` 检查点，随后重跑完整评估到 `output/existing_motion_diagnostics_20260925_run04/`：142 条单窗口和 12 条连续生成正常完成，设备为本机 RTX 4070 Laptop GPU。`center_validation.csv`、`rollouts.csv`、`rollouts_4frame.csv` 与之前的 `run03` 逐字节 SHA-256 一致；封版契约和两个检查点 SHA-256 也一致。因此本次未发现 E 盘数据缺失或读取导致的数值变化。此结论只覆盖本次实际读到的文件，不代表磁盘健康诊断。

### 单窗口：相同 Root 下的脚速和接缝

下表为验证集、每段一个中心窗口、**无参考**、来源 Root 输入。误差和脚速均为每段先聚合后等权平均。`接缝跳变`是历史最后一帧到未来首帧的全骨骼世界位移均值，并非凭视觉判定的断帧。

| 类别 | 段数 | uniform12 接触脚速 | hybrid12 接触脚速 | 源动作接触脚速 | hybrid12 接缝跳变 / 源动作 | 单位 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Walk | 50 | 0.612 | 0.546 | 0.043 | 6.73 / 5.95 | 脚速 m/s；跳变 cm |
| Run | 42 | 1.081 | 1.116 | 0.058 | 13.94 / 12.53 | 同上 |
| Crouch | 50 | 0.645 | 0.609 | 0.051 | 7.95 / 6.01 | 同上 |

这些均使用**完全相同的来源 Root**恢复世界脚位置，故本次离线脚速差异来自预测身体姿态随时间未能像源动作那样抵消 Root 运动；它不能单独定位为接触标签、损失设计、FK 或 UE 骨架映射中的哪一项。图中 Walk 1675、Crouch 393 的接触对分别有 21、18 个，模型速度持续高于源动作；Run 762 仅有 4 个接触对，作为局部异常而非全类代表。单窗首帧世界关节位置误差均值：hybrid12 Walk 3.56 cm、Run 5.33 cm、Crouch 4.66 cm。与归档 `validation_quality.json` 的同类姿态/脚速统计吻合在约 0.002 m/s 内。

### 连续生成：真实历史对照与重规划频率

下表只覆盖上述固定的**每类 4 条**片段。第 3 个 24 帧块误差为关节三维欧氏 RMSE；`真实历史`每次输入对应源帧，`回灌历史`输入此前实际生成的帧，两者使用同一时段的来源 Root。脚速统计整个 72 帧输出。

| 权重 / 类别 | 24 帧重规划：第 3 块真实历史 / 回灌历史 | 4 帧重规划：第 3 块真实历史 / 回灌历史 | 24 帧重规划脚速 | 4 帧重规划脚速 | 源动作脚速 |
| --- | ---: | ---: | ---: | ---: | ---: |
| hybrid12 / Walk | 8.92 / 23.17 cm | 4.66 / 25.85 cm | 1.18 | 1.29 | 0.03 m/s |
| hybrid12 / Run | 11.46 / 27.48 cm | 7.05 / 31.49 cm | 3.01 | 2.79 | 0.06 m/s |
| hybrid12 / Crouch | 8.45 / 20.74 cm | 5.56 / 22.79 cm | 1.34 | 1.50 | 0.05 m/s |
| uniform12 / Walk | 8.03 / 19.13 cm | 5.84 / 29.79 cm | 1.14 | 1.50 | 0.03 m/s |
| uniform12 / Run | 12.30 / 23.67 cm | 7.52 / 25.37 cm | 2.58 | 2.44 | 0.06 m/s |
| uniform12 / Crouch | 9.19 / 23.91 cm | 5.33 / 24.10 cm | 1.65 | 1.45 | 0.05 m/s |

同帧 teacher-forced 对照显示，后期误差增长中有明显的**生成历史回灌效应**。在本 12 条样本、来源 Root 条件下，重规划间隔从 24 缩短到 4 帧未消除该效应，部分场景更差；不能从这组小样本推断所有动作的最优间隔。24 帧重规划边界的跳变均值比源帧边界高约 0.4–1.1 cm，而第 3 块关节误差已达 20–27 cm 左右，故当前更大的连续性风险是反馈后的姿态漂移，而非单次边界跳变一个指标。

### 只用历史的 Root 基线

过去 6 个 Root 增量匀速外推在 142 段中有 119 段的未来第 24 帧位置误差小于 10 cm；23 段达到或超过 10 cm，11 段超过 50 cm。按资产 `phase=pivot` 的 7 段，末帧误差平均约 150.2 cm，最大 Run 836 为约 409.9 cm。此类方向切换的未来意图无法仅从过去的匀速轨迹确定。Root 计划偏差至少 50 cm 的 11 段中，hybrid12 的预测身体姿态相对原 Root 条件平均改变约 5.74 cm，说明模型对 Root 条件并非完全不响应；变化本身不能证明姿态合理或可玩。

## 结论与使用边界

- **直接测得：**无参考单窗的派生接触脚速显著高于源动作；相同来源 Root 下仍成立。12 条固定片段中，真实历史与回灌历史的同帧对照出现明显误差差距；4 帧重规划没有自动解决。过去轨迹匀速 Root 基线在 Pivot 等变向片段误差很大。
- **工程推断：**应优先研究模型对自身生成历史的鲁棒性和脚部时间约束，再分别比较接触/FK 约束、脚锁定/IK 以及训练时历史扰动；已有简单接触损失实验存在姿态误差取舍。未来 Root 需要玩家输入与 CMC/Mover 的可执行规划，历史外推只可作低门槛基线。
- **尚未验证：**UE CMC/Mover 真实玩家输入与 Root 轨迹、蒙皮、IK、胶囊体碰撞、可视脚滑、网络修正、跨片段切换、站蹲请求响应。过去 Root 外推不是控制器。原动作未来 Root 与源动作派生接触标签仍是离线条件；12 条长序列不足以宣称全类别泛化。本实验没有做新的 107 条人工验收，也未修改 P0 的确认结论。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-25 | 首次记录，采用完整 `run03`，保留先前输出 | 汇总 JSON、逐条 CSV、接触示例图 |
| 2026-09-25 | E 盘重读并重跑 `run04`；补充三段真实模型推理视频 | `run04` 逐条 CSV 哈希、MP4 和渲染清单 |
