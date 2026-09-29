# 现有 Walk/Run/Crouch 接触标签与速度覆盖审计

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-25-contact-speed-audit`；数据标签核查 / 已有模型分层评估 |
| 日期与时区 | 2026-09-25 +08:00；精确起始时间未记录 |
| 状态 | 完成数据诊断及同条件小规模训练消融；新增脚速度损失未通过验证，不采用 |
| 执行者与来源 | Codex 本机执行；AIAnimationSystem 封版来源动作、既有 `generated_contact10` 验证输出 |
| 前序记录 | [Root 与姿态配对的 UE 四路滑步对照](2026-09-25-root-pose-alignment.md)、[闭环与接触训练实验](2026-09-25-closed-loop-optimization.md) |

## 问题与方法

在继续提高接触约束前，先查三个问题：封版接触位是否与当前派生逻辑一致；Run 接触帧是否足以支持接触损失和评估；现有训练窗口与验证失败是否集中在某些 Root 速度。只审计 Walk、Run、Crouch；不把启发式接触位当物理真值，也不据此自动剔除片段。诊断后另做一组同条件训练消融，测试不依赖接触标签的世界脚速度轨迹监督。

封版接触定义为四个脚/脚掌骨的**世界脚速 <0.15 m/s 且绝对高度 <0.10 m**，速度使用前向帧差。核查时从 1217 条来源 NPZ 重新计算，逐位对照存储位；另外用“速度 <0.15 m/s、脚高低于该片段该脚高度第 5 百分位 +10 cm”做敏感性代理。这一代理仍不知道地面高度。Run 另固定高度阈值，分别把脚速阈值改成 0.20、0.30、0.50 m/s，**只统计新增覆盖，不改标签**。

速度分组使用 24 帧目标窗口的水平 Root 平均速度，分档为 `<0.2`、`0.2–1`、`1–2`、`2–4`、`≥4 m/s`。训练覆盖数来自封版 `windows.jsonl` 全部 Walk/Run/Crouch 窗口；同一片段的重叠窗口并非独立动作。模型基线直接复用上次固定的 **142 条验证集每片段一个中心窗口**、无未来姿态参考、**来源未来 Root**、`generated_contact10` 结果；分组前重新检查其 `clip_index` 与接触帧对数。模型分数没有重新推理，更不代表实时 CMC。

## 代码、数据与复现

- 仓库 HEAD `e07aad29773bf24dcadd98e36271d3af1894e7fe`；工作树含前序未提交实验，本次只新增本实验脚本、记录、证据和索引行。封版契约 SHA-256 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`；来源清单 SHA-256 `9a6c10fa2cd906c47f7f137cf5a83361e86fbbb40d2a7182d8e87c631145483a`。
- 封版目录：本机 `E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924`，来源 `E:\AIAnimationSystemData\prepared\native30_traversal_semantic_v1`，30 FPS、79 骨。封版 1722 条；本次核查 Walk 427、Run 396、Crouch 394 条。既有中心窗口 CSV SHA-256 `992ee5935478f6b3ae51afcb5150d7b3897eafc386645c62fa95c58e49a7b535`，来自[前序训练实验](2026-09-25-closed-loop-optimization.md)。项目 `.venv`：Python 3.12.12、NumPy 2.5.3、SciPy 1.18.1、PyTorch 2.14.0+cu130；数据审计用 CPU，后续训练和验证用本机 GPU。
- [接触与模型分层脚本](assets/2026-09-25-contact-speed-audit/audit_contact_speed.py)、[全窗口速度覆盖脚本](assets/2026-09-25-contact-speed-audit/audit_window_speed.py)、[Run 阈值敏感性脚本](assets/2026-09-25-contact-speed-audit/audit_run_thresholds.py)。运行时新建输出目录，不覆盖已有报告。

```powershell
$env:PYTHONPATH=(Get-Location).Path
$py='D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe'
$asset='docs/experiments/assets/2026-09-25-contact-speed-audit'
$release='E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924'
& $py "$asset/audit_contact_speed.py" --release $release --baseline-csv 'output/closed_loop_eval_20260925_run02/center_validation.csv' --output "$asset/result" --model generated_contact10
& $py "$asset/audit_window_speed.py" --release $release --output "$asset/result/window_speed.json"
& $py "$asset/audit_run_thresholds.py" --release $release --output "$asset/result/run_threshold_sensitivity_v2.json"
```

上面的第三个文件名保留了首次聚合阈值报告后的 `v2` 扩展：它补上了分速度档计数；[首次报告](assets/2026-09-25-contact-speed-audit/result/run_threshold_sensitivity.json)仍在，未覆盖。复现时输出必须使用新目录或新的文件名。

核查程序在独立 `output/contact_speed_audit_verify_20260925/` 复跑一次；汇总 JSON 和三份 CSV 与记录中的文件逐字节一致。仓库内 `summary.json`、`window_speed.json`、`run_threshold_sensitivity_v2.json` 的 SHA-256 分别为 `d99791fd0ed5e4e4d63e07a6b06e5ebfc3c47da9f969ac745be681910cab4664`、`b65dba4eaf095ad7189bf2a89f9765e897f1768382a9167c6e29e8c7645f2fa4`、`4544c8234838b9ffd7f432c38f64433801abe6bf12ec97d3772b641bf94debd6`。

## 结果

### 标签覆盖与可信边界

1217 条存储接触位与从原始姿态及 Root 重新派生的结果**逐位一致**。这排除了索引写错或读取错位，**不能证明物理接触正确**。以下是所有分区的来源数据统计；“无连续接触”指整条片段没有相邻两帧同时接触，仍可能有单帧标签。

| 类别 | 片段数 | 接触位占四脚总帧位 | 连续接触帧对 | 单帧接触段占比 | 无连续接触片段 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Walk | 427 | 27.86% | 60,758 | 6.41% | 1 |
| Run | 396 | 12.47% | 15,499 | 19.42% | 2 |
| Crouch | 394 | 28.31% | 52,821 | 8.79% | 0 |

Run 的接触覆盖和连续性明显更弱。验证集中心窗口里，`≥4 m/s` 的 7 条 Run 只有 **8 个**接触帧对，2 条完全没有；`2–4 m/s` 的 29 条有 133 个帧对。把速度阈值从 0.15 提至 0.30 m/s 后，高速组的帧对从 8 到 32，`2–4` 组从 133 到 216；[阈值敏感性报告](assets/2026-09-25-contact-speed-audit/result/run_threshold_sensitivity_v2.json)保留了四档结果。增加的帧对可能包含滑动脚，不能直接改成真接触。局部地板高度代理较原标签额外标出 Walk/Run/Crouch 总脚帧位的 7.57%/1.60%/6.51%，也只能作为复核候选。

### 训练数据的速度覆盖

| 类别 | 训练窗口总数 | 0.2–1 m/s 窗口 | 其中稳定速度窗口 | 验证集中 0.2–1 m/s 窗口 |
| --- | ---: | ---: | ---: | ---: |
| Walk | 8,353 | 103（1.23%） | 19 | 5 |
| Run | 4,781 | 32（0.67%） | 2 | 0 |
| Crouch | 6,807 | 50（0.73%） | **0** | 21 |

“稳定”是窗口内逐帧 Root 速度标准差 <0.10 m/s。0.2–1 m/s 窗口多数是起停过渡，不等于匀速慢走/慢蹲素材；重叠窗口也不能当作同数目的独立动作。训练速度分布详见[全窗口表](assets/2026-09-25-contact-speed-audit/result/window_speed.json)。现有数据对匀速慢行的监督很弱，尤其是蹲行。

### 已有模型在验证集中的速度分层

接触脚速按来源接触位选相邻帧对，先在每条片段平均，再对片段等权平均。来源脚速本身被 `<0.15 m/s` 的标签规则选低了，所以不应把它解释成独立测得的物理真值；两栏仍在**同一批来源标记帧**上可比。

| 类别 / 来源 Root 平均速度 | 片段数 | 接触帧对 | 来源脚速 | 模型脚速 | 模型姿态 RMSE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Walk / 1–2 m/s | 40 | 858 | 0.049 m/s | 0.503 m/s | 6.32 cm |
| Run / 2–4 m/s | 29 | 133 | 0.065 m/s | **1.064 m/s** | 9.44 cm |
| Run / ≥4 m/s | 7 | **8** | 0.075 m/s | 1.188 m/s | 9.52 cm |
| Crouch / 1–2 m/s | 27 | 544 | 0.058 m/s | 0.662 m/s | 9.81 cm |
| Crouch / 2–4 m/s | 15 | 300 | 0.062 m/s | 0.704 m/s | 8.62 cm |

全 142 条的等权平均：Walk 模型/来源 0.480/0.043、Run 0.933/0.058、Crouch 0.588/0.051 m/s。[完整分速度及动作阶段汇总](assets/2026-09-25-contact-speed-audit/result/summary.json)和[逐条验证 CSV](assets/2026-09-25-contact-speed-audit/result/validation_scores.csv)包含静止、start/stop/pivot/turn 等小组及接触样本数。原资产属于 Run 的 6 个验证中心窗口实际速度低于 0.2 m/s；类别名不能代替逐帧运动状态。此前匹配 CMC 的[UE 四路视频](2026-09-25-root-pose-alignment.md)是独立视觉证据，而本表使用来源未来 Root 的离线成绩，两者不可直接合并成同一测试集。

### 同起点脚速度轨迹训练消融：未带来稳定收益

基于审计后，在本机 RTX 4070 Laptop GPU 运行[匹配训练脚本](assets/2026-09-25-contact-speed-audit/train_foot_velocity_ablation.py)。两臂均从既有 `generated_contact10` 权重 SHA-256 `d5e1176444238c243d8836bd2b8139485a2ec8e607ea4a5cdb7fb5a14a69ee5a` 出发，使用同样的 **938 条训练片段**、随机种子 `20260925`、每轮相同窗口与打乱顺序、batch 8、学习率 `3e-5`、3 轮各 118 批、75% 生成历史回灌、接触权重 `0.0005`，未来姿态参考关闭。`control3` 只继续现有损失；`foot_velocity3` 另以权重 `0.01` 加入四个脚骨世界速度**矢量**相对源动作的 SmoothL1（`beta=0.5 m/s`，全部未来相邻帧）。训练 Root 和目标姿态仍是成对的同条来源动作。两组都从相同起点训练相同步数，避免把单纯多训当新损失收益。[生效配置](assets/2026-09-25-contact-speed-audit/training/config.json)及[对照训练曲线](assets/2026-09-25-contact-speed-audit/training/control_metrics.json)、[实验训练曲线](assets/2026-09-25-contact-speed-audit/training/foot_velocity_metrics.json)已保存。

```powershell
$env:PYTHONPATH=(Get-Location).Path
$py='D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe'
& $py 'docs/experiments/assets/2026-09-25-contact-speed-audit/train_foot_velocity_ablation.py' --output 'E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_foot_velocity_ablation01' --epochs 3 --batch-size 8 --lr 3e-5 --seed 20260925 --contact-weight 0.0005 --foot-velocity-weight 0.01
& $py 'docs/experiments/assets/2026-09-25-existing-motion-diagnostics/evaluate_existing_motion.py' --output 'output/contact_speed_foot_velocity_eval_20260925' --checkpoint 'initial=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02\generated_contact\epoch_010.pt' --checkpoint 'control3=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_foot_velocity_ablation01\control\epoch_003.pt' --checkpoint 'foot_velocity3=E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_foot_velocity_ablation01\foot_velocity\epoch_003.pt'
& $py 'docs/experiments/assets/2026-09-25-contact-speed-audit/summarize_ablation.py' --speed-map 'docs/experiments/assets/2026-09-25-contact-speed-audit/result/validation_scores.csv' --evaluation 'output/contact_speed_foot_velocity_eval_20260925' --output 'docs/experiments/assets/2026-09-25-contact-speed-audit/result/ablation_summary.json'
```

命令重跑时应换全新输出路径；上面记录的是本次实际路径。初步 16 片段、1 轮的本机运行输出保存在 `output/contact_speed_foot_velocity_smoke_20260925/`。正式权重只在本机 E 盘；`control3` SHA-256 `a490934e78ab27abdddfef0764753d2bf4dfd9c044c7d4edf03ffbaf76b761b3`，`foot_velocity3` SHA-256 `8b28a6b6d4788e08b4525c8e885d8ebde4f2707faae99ed8b9eb179eafcda993`。离线验证包含每类各 50/42/50 条的中心窗口及每类 4 条固定 72 帧连续生成，全部是**验证分区、无未来姿态参考、来源未来 Root**；没有在新实验中查看或调试测试分区。[完整评估摘要](assets/2026-09-25-contact-speed-audit/evaluation/summary.json)、[中心窗口 CSV](assets/2026-09-25-contact-speed-audit/evaluation/center_validation.csv)、[长序列 CSV](assets/2026-09-25-contact-speed-audit/evaluation/rollouts.csv)与[速度分组表](assets/2026-09-25-contact-speed-audit/result/ablation_summary.json)随记录保存。

| 验证集类别 | 起点脚速 m/s | 同步数对照脚速 m/s | 加脚速度损失后脚速 m/s | 对照姿态 RMSE / 实验姿态 RMSE |
| --- | ---: | ---: | ---: | ---: |
| Walk，50 条 | 0.480 | 0.447 | 0.445 | 5.82 / 5.85 cm |
| Run，42 条（40 条有接触分数） | 0.933 | **0.940** | **0.946** | 8.75 / 8.77 cm |
| Crouch，50 条 | 0.588 | **0.580** | **0.591** | 8.65 / 8.70 cm |

在数据较充足的 Run `2–4 m/s` 组（29 条、133 来源接触帧对），对照/实验脚速为 **1.070/1.095 m/s**；Crouch `1–2` 和 `2–4 m/s` 两组也都略退步。Run `≥4 m/s` 的实验组虽比对照低 0.093 m/s，但仅 **8 个**来源接触帧对，不足以据此选模型。12 条固定长序列中，第 3 块姿态误差及全段脚速也未出现稳定优势：Walk 19.26/0.981→19.21/0.973，Run 19.51/2.249→19.56/2.237，Crouch 19.67/1.288→19.68/1.278（cm / m/s；箭头为对照到实验，每类仅 4 条）。训练轨迹项本身下降了，但验证的落脚和姿态没有同步改善。

**决定：不采用 `foot_velocity3` 作为下一版模型，不投入 UE 新蒙皮渲染或冻结测试。**这是单一种子、有对照的负结果，不能据此否定所有轨迹约束；目前只否定本次输入、损失权重及 3 轮续训组合。

## 结论与下一步门槛

- **直接测得：**索引接触位与当前规则一致；Run 尤其高速窗口的连续接触监督稀疏；现有稳定慢速训练窗口极少；已有模型在常见移动速度上仍有明显脚滑；本次额外世界脚速度轨迹损失没有在同训练步数验证对照中稳定改善结果。
- **工程判断：**先从[复核候选清单](assets/2026-09-25-contact-speed-audit/result/review_queue.csv)中检查高速 Run 与可能的地板高度偏移，确定可用的接触段和无标签段。训练消融应同时保留“姿态误差不变坏”的门槛，先比较同数据、同模型的速度/相位分层与轻量世界脚轨迹约束，再考虑接触状态预测。慢速匀速蹲行没有足够独立监督；只能作为当前数据缺口，若暂不补采，可先试一致的 Root+姿态时间缩放增强并单独验证，不能把结果写成真实采集质量。
- **尚未验证：**复核候选的人工物理接触真值、可靠地面高度、慢速增强后的真实性、真实玩家/CMC 转弯起停效果。本次训练没有修改模型结构或封版标签与划分，也没有新的 UE 蒙皮视频；验证负结果不替代真实玩家效果测试。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-25 | 首次记录，保留 Run 阈值报告初版并补上速度分档版 | 1217 条来源核查、训练窗口覆盖、142 条既有验证分数 |
| 2026-09-25 | 增补同起点 3 轮脚速度轨迹损失消融，记录负结果 | 双臂配置、权重哈希、142 条中心窗口和 12 条长序列验证 |
