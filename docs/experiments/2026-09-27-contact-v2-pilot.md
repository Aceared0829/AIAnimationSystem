# 接触候选与速度采样短训练：离线和 UE 蒙皮对照

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 日期 | `2026-09-27-contact-v2-pilot`；2026-09-27 +08:00 |
| 类型 / 状态 | 数据标签诊断、三臂短训练、离线评估、UE 蒙皮复核；**完成，两个候选均不采用** |
| 前序 | [接触/速度审计](2026-09-25-contact-speed-audit.md)、[训练设计](2026-09-26-contact-review-training-design.md)、[Root 与姿态配对的 UE 对照](2026-09-25-root-pose-alignment.md) |
| 执行环境 | 本机 RTX 4070 Laptop、PyTorch 2.14.0+cu130；UE 5.8.1 NNE CPU 自动化 |

## 目标与结论

按照前序计划，分别试了接触标签的保守候选补充、速度/动作阶段重采样，并在同一初始模型、同一封版数据和同一验证条件下比较。最后把较有希望的速度/阶段组放进 UE，使用**相同来源片段、相同已录制且与来源运动匹配的 CMC Root** 做蒙皮对照。

结果没有达到落脚修复门槛。接触候选组相对训练对照几乎不变；速度/阶段组在部分离线分组略好，但 Walk 变差，Run 四帧重规划的第三块姿态误差从 **23.42 cm 升至 27.96 cm**，脚速从 **2.63 升至 2.81 m/s**。UE 中 Run 的接触脚速仍为 **3.83 m/s**，与训练对照相同量级；来源动作在相同 Root 上为 **0.066 m/s**。这两个检查点只保留作诊断，不替换当前模型。

## 数据与标签诊断

封版目录为本机 `E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924`。契约 SHA-256 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`，来源清单 SHA-256 `9a6c10fa2cd906c47f7f137cf5a83361e86fbbb40d2a7182d8e87c631145483a`。代码基点 `e07aad29773bf24dcadd98e36271d3af1894e7fe`，实验工作树有前序未提交文件；本轮未修改封版文件、原接触位或用户验收结论。

[诊断脚本](assets/2026-09-27-contact-v2-pilot/contact_v2_audit.py)重读 train/validation 的原动作和 Root，校验来源哈希并逐位验证原接触位。新的 `0.5` 权重只加在**同侧 toe 已有接触位、foot 世界速度 <0.15 m/s、foot 高度低于该片段该脚 p05+8 cm、原 foot 位为 0** 的帧；原接触位权重仍为 `1.0`。它是候选训练监督，**不是人工确认或物理接触真值**，没有写回源数据。

| 核查范围 | Walk | Run | Crouch |
| --- | ---: | ---: | ---: |
| 训练片段数（含过短片段） | 331 | 316 | 299 |
| 训练原接触位 | 53,891 | 15,986 | 44,548 |
| 候选新增 foot 位 | 13,870 | 2,109 | 10,031 |
| 30 条重点复核片段数 | 8 | 14 | 8 |
| 重点片段原连续接触帧对 | 195 | **26** | 530 |
| 候选后加权帧对 | 220 | **26** | 573.25 |

Run 重点片段的候选没有增加连续接触帧对，说明这条保守规则无法补上最困难的监督缺口。[汇总](assets/2026-09-27-contact-v2-pilot/audit/audit_summary.json)、[逐条候选表](assets/2026-09-27-contact-v2-pilot/audit/candidate_review.csv)与 [Run 857](assets/2026-09-27-contact-v2-pilot/audit/contact_857.png)、[Walk 1587](assets/2026-09-27-contact-v2-pilot/audit/contact_1587.png)、[Crouch 201](assets/2026-09-27-contact-v2-pilot/audit/contact_201.png)逐帧图保留原因证据。局部脚高度仍不能替代地面碰撞/物理接触测量。

## 匹配训练

三个训练臂均从同一 `generated_contact/epoch_010.pt` 开始，初始检查点 SHA-256 `d5e1176444238c243d8836bd2b8139485a2ec8e607ea4a5cdb7fb5a14a69ee5a`。只用 Walk/Run/Crouch 的 938 条长度至少 72 帧的**训练片段**。均训练 3 epoch、batch 8、AdamW、学习率 `3e-5`、seed `20260927`、接触损失权重 `0.0005`，生成历史概率 `0.75`；输入不含未来姿态参考，但训练配对的是**来源未来 Root**。

| 训练臂 | 单独变化 | 检查点 SHA-256 |
| --- | --- | --- |
| `control` | 原接触位、普通随机片段/窗口 | `6b9bee84e583324928e024c94d3b8c4d1fe3017e4ace23acade49f9fe16c03f0` |
| `toe_witness` | 与 control 相同片段/窗口/顺序；加上述半权重 foot 候选 | `ad6b050d606921f09a1548d533044939e638b6e047a4f29a31ca816069a207f8` |
| `speed_phase` | 原接触位；按类别/阶段/整片段速度档稀缺度，80% 常规 + 20% 重采样，每片段最多两次 | `d924308f2635512c15292774dfb6ffc860963791b710b71a204eec844ef9fd5b` |

`speed_phase` 每 epoch 仍抽 938 次，独立片段为 792/797/792 条，其余为重复抽样，不能当作补齐了数据。训练权重只在本机 `E:\AIAnimationSystemData\training_runs\conditioned_pose_20260927_contact_v2_pilot01`；[训练脚本](assets/2026-09-27-contact-v2-pilot/train_matched_pilot.py)、[完整配置](assets/2026-09-27-contact-v2-pilot/training/config.json)、三臂逐 epoch 指标及[抽样计划](assets/2026-09-27-contact-v2-pilot/training/speed_phase_sampling_plans.json)留在仓库工作树。本地短训练无需远程卡，因此查看 Compshare 控制台后没有启动实例或传输数据；本实验**未使用云 GPU**。

## 离线验证

用同一封版 validation：Walk 50、Run 42、Crouch 50 条，每条中心窗口等权；另有每类 4 条长序列分别做 72 帧块和四帧重规划。**都没有未来姿态参考；离线评分/长序列仍用来源未来 Root**，不等于玩家实时控制结果。脚速是在相同来源启发式接触位对应的脚帧对上计算，来源脚速也被该标签规则选低，不能当独立物理真值。

| 类别 | control：姿态 / 接触脚速 | toe_witness：姿态 / 接触脚速 | speed_phase：姿态 / 接触脚速 |
| --- | ---: | ---: | ---: |
| Walk | 5.891 cm / 0.464 m/s | 5.885 / 0.463 | 5.907 / **0.467** |
| Run | 8.783 cm / 0.936 m/s | 8.780 / 0.935 | 8.772 / 0.922 |
| Crouch | 8.644 cm / 0.577 m/s | 8.645 / 0.577 | 8.584 / 0.572 |

Run 的单窗小幅改善没有延续到四帧重规划。此时 `speed_phase` 第三块姿态 RMSE **27.96 cm**（control 23.42），接触脚速 **2.81 m/s**（control 2.63），且 4 条长序列样本量很小。30 条重点片段的重新评分也显示 `toe_witness` 在 Crouch 候选脚速 **0.11802 m/s**（control 0.11768），Run 候选帧对仍为 26；没有一致收益。[完整分档汇总](assets/2026-09-27-contact-v2-pilot/validation_summary.json)、[142 条逐条 CSV](assets/2026-09-27-contact-v2-pilot/evaluation/center_validation.csv)、[长序列 CSV](assets/2026-09-27-contact-v2-pilot/evaluation/)与[30 条复核评分](assets/2026-09-27-contact-v2-pilot/review_eval/review_summary.json)保留全部结果。

## UE 蒙皮和实际效果

尽管离线门槛未通过，仍把 `control` 与 `speed_phase` 各导出一次 ONNX，配同一录制 CMC 轨迹，在 UE `AIAnimation.Lab.RootPoseFourWay` 自动化中分别跑 Walk/Run/Crouch 各 72 帧。两个 fixture 的来源姿态、来源 Root、接受的 CMC Root 和来源接触位逐字节相同。两轮测试均 `Result={Success}`；NNE 与 Python ORT 差异在日志的九位小数精度下为 `0.000000000`，脚骨读回与预期差异 `0.000000 cm`。这确认了推理/骨骼写入路径，不能说明脚落地正确。[UE 摘要：control](assets/2026-09-27-contact-v2-pilot/ue_control_summary.json)、[UE 摘要：speed_phase](assets/2026-09-27-contact-v2-pilot/ue_speed_phase_summary.json)、[ONNX 清单](assets/2026-09-27-contact-v2-pilot/ue_onnx_control_manifest.json)、[fixture 清单](assets/2026-09-27-contact-v2-pilot/ue_fixture_control_manifest.json)、[自动化关键日志](assets/2026-09-27-contact-v2-pilot/ue_test_evidence.txt)。

| UE 片段（同一 CMC Root） | 来源姿态接触脚速 | control 模型 | speed_phase 模型 | 结论 |
| --- | ---: | ---: | ---: | --- |
| Walk 1587；validation；61 帧对 | 0.039 m/s | 0.399 | 0.394 | 轻微下降，仍约来源 10 倍 |
| Run 1109；**train**；19 帧对 | 0.066 m/s | 3.833 | **3.834** | 没有改善 |
| Crouch 146；validation；46 帧对 | 0.065 m/s | 0.688 | 0.664 | 略降，仍约来源 10 倍 |

Run 为诊断视觉片段，来自训练集，**不能充当独立测试集效果**；离线 Run 的 42 条 validation 另见上一节。这里的平均脚速按来源标签选帧，并非人工标注足底接触。

直接看 3 路同屏蒙皮视频（左：来源姿态；中：control；右：speed_phase；都配同一 CMC Root）：[Walk](assets/2026-09-27-contact-v2-pilot/media/walk_control_vs_speed_phase.mp4)、[Run](assets/2026-09-27-contact-v2-pilot/media/run_control_vs_speed_phase.mp4)、[Crouch](assets/2026-09-27-contact-v2-pilot/media/crouch_control_vs_speed_phase.mp4)。每段 72 个源帧以 15 FPS 播放，故画面为半速；亮度增强仅为展示。还有[Run 接触帧静图](assets/2026-09-27-contact-v2-pilot/media/run_poster.png)、[三类脚速轨迹](assets/2026-09-27-contact-v2-pilot/ue_foot_speed.png)及[视频哈希/展示变换清单](assets/2026-09-27-contact-v2-pilot/media/manifest.json)。UE 用 UEFN Mannequin `UPoseableMesh`、NNE CPU、平面无碰撞地板和录制 CMC Root 回放；**不是实时玩家输入、AnimGraph/CharacterMovement 闭环或物理触地测试**。

## 原因判断与下一轮门槛

本轮可以排除“只因显示时 Root 错配”“ONNX 或 UE 写骨误差”“简单增加接触候选或重复稀缺速度片段即可治好”的解释。证据支持更具体的限制：Run 有效接触监督太稀，候选规则没有补出连续帧对；原模型在来源未来 Root 条件下训练，离线的小幅改进不能直接迁移到真实控制器 Root；当前姿态输出缺少可靠的脚底接触状态与速度一致性闭环。上述是对结果的工程推断，还需独立测试确认主因。

下一轮先在 UE 用玩家/CMC 的实际在线 Root、速度、朝向和 Stand/Crouch 状态录制输入与骨骼脚轨迹，建立**无来源未来 Root** 的固定测试集；再按地面高度/法线与脚底轨迹人工复核 Run 接触窗口。通过后再试显式触地状态、脚部世界轨迹/FK 约束或受限 IK 修正。候选须同时降低 Walk/Run/Crouch 的接触段漂移，且不恶化四帧重规划姿态与接缝，才进入玩家闭环。现有 `speed_phase` 不能作为新默认模型。

## 复现与证据位置

可直接执行的关键步骤如下；输出目录需使用新路径，避免覆盖本轮证据。辅助脚本路径、CLI 参数和 UE 自动化启动方式参见上述前序记录及各脚本 `--help`。本机路径是作者机器的归档位置。

```powershell
$env:PYTHONPATH=(Get-Location).Path
$py='D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe'
$asset='docs/experiments/assets/2026-09-27-contact-v2-pilot'
$release='E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924'
& $py "$asset/contact_v2_audit.py" --release $release --baseline 'output/closed_loop_eval_20260925_run02/center_validation.csv' --queue 'docs/experiments/assets/2026-09-25-contact-speed-audit/result/review_queue.csv' --output 'output/contact_v2_audit_reproduction'
& $py "$asset/train_matched_pilot.py" --output 'E:\AIAnimationSystemData\training_runs\conditioned_pose_contact_v2_reproduction'
```

评估使用[既有无参考脚本](assets/2026-09-25-existing-motion-diagnostics/evaluate_existing_motion.py)和上述三臂检查点；UE 使用[配对 fixture 脚本](assets/2026-09-25-root-pose-alignment/build_matched_fixtures.py)、[UE 自动化测试](../../unreal-script/AIAnimation/Source/AIAnimation/Private/AIAnimationConditionedSkinningTests.cpp)、[脚骨读回分析脚本](assets/2026-09-25-root-pose-alignment/analyze_four_way.py)、[三路视频打包脚本](assets/2026-09-27-contact-v2-pilot/package_ue_comparison.py)。大体积的 ONNX、原始 UE 帧/脚骨 CSV 和评估临时输出仍在本机 `output/contact_v2_ue_20260927/`、`output/contact_v2_pilot_eval_20260927/`，没有纳入轻量实验包。

## 修订历史

- 2026-09-27：完成候选标签审计、三臂短训练、142 条 validation 与 12 条长序列对照，以及两个模型的 UE 蒙皮视频；判定候选不采用。
