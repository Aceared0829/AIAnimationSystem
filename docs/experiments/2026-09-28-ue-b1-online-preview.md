# UE 单机 CMC + B1 在线姿态预览

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-28-ue-b1-online-preview`；模型导出 / 本地 UE 推理 / 单机功能试验 |
| 时间与时区 | 2026-09-28 约 19:45–20:46，Asia/Hong_Kong；CSV 文件名采用 UTC |
| 状态 | 集成和自动场景通过；自由回灌姿态质量未通过 |
| 执行者与来源 | 本项目本地实验；B1 权重来自 [站蹲条件训练](2026-09-28-stance-transition-v2.md)，GASP 宿主内容属于外部项目 |
| 前序 | [CMC 执行 Root 观测](2026-09-28-ue-cmc-preview.md) |

## 问题与方案

验证 B1 权重能否在 UE 5.8.2 的真实单机 CMC 角色上以本地 DirectML 运行，并让姿态跟随角色，而不由模型推动 Actor Root。对照两种历史：默认读取 GASP 原 AnimInstance 姿态；诊断模式把上次模型可见姿态回灌到下一次历史。二者使用相同权重、同一 CMC 顶棚站蹲测试、实际被 CMC 接受的 Stand/Crouch 状态。关心初始化/推理失败、可见姿态、执行 Root 与意图状态，以及两种历史下姿态是否漂移。

这不是完整的下一版控制契约：未来 Root 仅由当前 CMC 速度常量外推 24 帧，不是 CMC 路径规划或真实未来；未接模型自有 Root 预测、Mover、AnimGraph、接触/IK、监听服务器或网络回滚。训练时的未来 Root 是来源动作真值，在线条件分布不一致。

## 代码、环境与数据

- 仓库基线：工作树 `codex/motionweaver-stance-root`，原始提交 `e07aad2`；本次代码/记录尚未提交，且该树包含前序 B1 与 CMC 演示改动。
- 宿主：本机 `D:\GameAnimationSample\GameAnimationSample.uproject`，UE `D:\UE_5.8` 5.8.2，Windows，NNE `NNERuntimeORTDml`。宿主插件目录通过 junction 指向本工作树的 `unreal-script/MotionWeaverCMCPreview`，没有修改原 `AIAnimation` 插件。
- B1 权重：仅本机 `E:\AIAnimationSystemData\training_runs\stance_pilot_20260928_cloud\run_b1\best.pt`，SHA-256 `317e0a5cbfeaeb2f9ae780087256ad4a267238f74bc59b90d09bd85f129a9c52`。
- 站蹲契约：`E:\AIAnimationSystemData\prepared\stance_root_pose_v2_p0_20260928_r2/contract.json`，SHA-256 `41436aaa999486212ae1bb1d955578f7cb5618ff59e95219cef13152a2a110a9`；基础契约 SHA-256 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`。
- 导出模型：仅本机 `E:\AIAnimationSystemData\exports\stance_pilot_b1_ue_20260928_v3/model.onnx`，SHA-256 `9c0a1d5fec04840e14d318c3560710f786218035a2f413a9e3e207d9d9b00d2d`；同目录 `manifest.json` SHA-256 `0a7d5c8667fd51643e2746d1dadcbd252d62c702adf34877a01469c346ac2bda`。骨架 SHA-256 `1a799ca14585ce18edcfce3bb755dc7adcffa84d5111ac3afa2aa71238b8b547`。
- 模型输入输出固定为历史 `1×24×718`、未来 Root `1×24×7`、未来目标蹲伏 `1×24×1`、输出 `1×24×711`，79 骨。历史名义 30 Hz，在低帧率时不补帧；每 4 个已采样历史帧做一次同步推理。模型只更新 `PoseableMeshComponent`，角色 CMC/Actor Root 和碰撞不受模型输出驱动。
- 导出器用零硬参考姿态与零 mask，将连续 0/1 目标映射到原 B1 的 Stand/Crouch embedding。固定种子 42 的输入上，包装器相对原 B1 前向最大绝对差 `9.54e-7`；ONNX Runtime CPU 相对包装器 `2.86e-6`。这仅证明数值接线，不证明动作质量。

主要复现命令（均在该工作树根目录执行；本机路径需按实际安装调整）：

```powershell
& 'D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe' -m inference.export.export_stance_pilot_onnx --checkpoint 'E:\AIAnimationSystemData\training_runs\stance_pilot_20260928_cloud\run_b1\best.pt' --stance-contract 'E:\AIAnimationSystemData\prepared\stance_root_pose_v2_p0_20260928_r2' --output 'E:\AIAnimationSystemData\exports\stance_pilot_b1_ue_20260928_v3'
& 'D:\UE_5.8\Engine\Build\BatchFiles\Build.bat' GameAnimationSampleEditor Win64 Development '-Project=D:\GameAnimationSample\GameAnimationSample.uproject' -WaitMutex -NoHotReloadFromIDE
& .\unreal-sample\Run-StanceModelPreview.ps1 -AutoTest
& .\unreal-sample\Run-StanceModelPreview.ps1 -AutoTest -Feedback
```

`L_CMCPreview` 和模型 Actor 由 `create_cmc_preview.py`、`add_stance_model_preview.py` 在 GASP 宿主生成；`.umap/.uasset` 未纳入仓库，不能在无 GASP 资产机器上直接复现。脚本默认源历史；`-Feedback` 只用于诊断漂移。

## 结果与证据

| 指标 | GASP 源历史 | 模型输出回灌 | 口径 |
| --- | ---: | ---: | --- |
| 自动场景/模型推理 | 通过；40 次，0 失败 | 通过；40 次，0 失败 | 单次顶棚站蹲路线；CMC 拒绝起身、离开后站起 |
| 推理耗时均值 / P95 / 最大 | 4.247 / 5.823 / 8.550 ms | 3.880 / 5.500 / 6.364 ms | 仅同步 `RunSync` 墙钟；每次推理一行 |
| 模型与同帧 GASP 79 关节差异均值 / P95 / 最大 | 7.930 / 12.227 / 17.108 cm | 27.964 / 42.015 / 46.807 cm | 同帧组件空间关节位置欧氏距离的 79 骨均方根，再对 40 行聚合；**不是对真值的模型 RMSE** |
| 请求/实际蹲伏不一致 | 14/40 行 | 14/40 行 | 顶棚阻挡期间，推理条件使用实际 `IsCrouched()` |

小型原始证据：[源历史 CSV](assets/2026-09-28-ue-b1-online-preview/source_history.csv) SHA-256 `3c56d18451f629d3037119fa4fbce3a0490c093df6caa26a1d2`；[输出回灌 CSV](assets/2026-09-28-ue-b1-online-preview/generated_feedback.csv) SHA-256 `9a4d5c5de2d64f18ab77e43d5f1776b737845b3ad837c5e2514055729a6e7ba6`。P95 是排序后第 `ceil(0.95×40)` 个样本。未纳入仓库的本机截图：`D:\GameAnimationSample\Saved\MotionWeaver\cmc_blocked_20260928T115252Z.png`、`cmc_standing_20260928T115254Z.png`（源历史）及 `cmc_blocked_20260928T115116Z.png`、`cmc_standing_20260928T115118Z.png`（回灌）。截图/GASP 素材只供本机验证，不对外分发。

人工视觉检查了以上四张自动场景截图：源历史模式有可辨认的蹲伏与恢复站立；模型回灌模式在站立后仍明显前倾。截图无法证明完整动画流畅度或落脚准确性；尚无长时间自由操控的人工验收。初始化失败的早期诊断运行在修复后重新执行，最终通过数据只来自后两次成功运行。

最终版本重新编译通过，并用交付脚本在 12:43 UTC（默认）与 12:45 UTC（`-Feedback`）再次各跑一轮自动场景：两轮日志均有 `MW_MODEL_READY`、`MW_CMC_AUTO_TEST_PASS`、`MW_MODEL_END: inference=40 failures=0 visible=1`。上述表格仍引用已归档的前一对 CSV；这两轮只作最终代码与启动脚本冒烟检查，不把不同运行的指标混算。

## 结论与论文使用边界

- **直接测得：** B1 ONNX 在 UE 单机 GASP CMC 角色上经本地 DirectML 成功初始化、推理并驱动可见姿态；两种模式各 40 次推理、零推理失败；CMC 顶棚站蹲场景仍按实际位移/碰撞执行。
- **基于结果的推断：** 源历史模式可作为接线演示；输出回灌与在线 Root 条件下存在明显闭环分布漂移，不能作为合格玩家动画。差异指标只是与 GASP 的偏离度，不能单凭它判定真值误差。
- **尚未验证：** 真实 30 Hz 采样、连续生成历史的稳定性、实际 CMC 未来轨迹、速度突变与转向、脚接触与滑步、长时间自由试玩、AnimGraph/NNE 产品化、Model Root 与 Mover 选择模式、监听服务器同步/预测/回滚。不能把本演示描述成这些能力已完成。
- **后续：** 首先采集在线可见条件的训练窗口，并用生成历史回灌及短/长时漂移评测闭环；然后换真实 CMC 计划轨迹、接触/IK、最终入 AnimGraph；单机质量达到门槛后再验监听服务器。保留 Model Root 预测作为独立可选模式。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-28 | 首次记录 B1 UE 接线、源历史/回灌对照与失败边界 | UE 自动场景截图、CSV、导出数值检查 |
