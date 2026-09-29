# 接触候选复核与下一轮训练设计

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-26-contact-review-training-design`；封版来源动作诊断 / 训练设计 |
| 日期 | 2026-09-26，Asia/Hong_Kong |
| 状态 | 30 条候选定量复核完成；3 条骨架播放器抽看；训练方案待实施 |
| 前序 | [接触标签、速度覆盖与负结果](2026-09-25-contact-speed-audit.md)、[UE Root/姿态四路对照](2026-09-25-root-pose-alignment.md) |

![下一轮训练设计图](assets/2026-09-26-contact-review-training-design/training-design-image25.png)

## 范围与证据

沿用前序从验证集选出的 [30 条候选清单](assets/2026-09-25-contact-speed-audit/result/review_queue.csv)，其中 Run 14、Crouch 8、Walk 8 条。封版契约 SHA-256 为 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`。所有 30 条均从本机 `E:\AIAnimationSystemData\prepared\native30_traversal_semantic_v1` 按契约逐条校验原始 NPZ 哈希，检查资产 ID、存储接触位及既有 24 帧中心窗口计数。结果见 [逐条 CSV](assets/2026-09-26-contact-review-training-design/result/review_metrics.csv) 和 [汇总 JSON](assets/2026-09-26-contact-review-training-design/result/review_metrics_summary.json)。

接触位原规则：四个脚骨/脚趾骨的世界脚速 `<0.15 m/s` 且世界绝对高度 `<0.10 m`。本次拆开统计“速度够低但高度不够低”与“高度够低但速度不够低”；`0.30 m/s` 速度阈值及每骨局部高度第 5 百分位 `+0.10 m` 仅是**敏感性探针**，不是新真值，也没有回写封版数据或训练标签。统计单位“帧位”指一帧的一个脚/脚趾骨；“帧对”指相邻两帧同一骨骼都标记接触。

30 条候选绑定至现有 Motion Review 队列，使用既有播放器抽看了 Run `824`、Run `857` 和 Crouch `201` 的中段骨架及 Root 轨迹。播放器把整条 Root 轨迹放入视野，脚部较小，只能确认动作和轨迹可读，不能判定物理地面接触、碰撞或蒙皮穿透。没有把任何候选自动标记“通过/不通过”；现有本机人工决策不参与下面的统计。[队列准备脚本](assets/2026-09-26-contact-review-training-design/prepare_review_queue.py)和 [固定队列](assets/2026-09-26-contact-review-training-design/review_queue/review_queue.json)保留复核入口。

## 复核发现

| 候选组 | 24 帧中心窗口原接触帧对 | 低速但高于绝对高度阈值 | 低于绝对高度阈值但脚速过高 | 探针帧对变化 |
| --- | ---: | ---: | ---: | --- |
| Run，14 条 | 26；2 条中心窗口为 0 | 7 帧位 | 257 帧位 | 速度阈值 0.30：26 → 71 |
| Crouch，8 条 | 530 | **181 帧位，全部在 right_foot** | 17 帧位 | 局部高度代理：530 → 703 |
| Walk，8 条 | 195 | 107 帧位，在左右 foot 骨 | 185 帧位 | 局部高度代理：195 → 288 |

Run `857` 和 `885` 的中心窗口都没有连续接触帧对，但完整片段分别有 7 和 26 对；这是**窗口位置与高速脚速门槛叠加**，不是整条动作没有脚落地。Run 14 条中心窗口累计只有 70 个低脚速帧位，原接触位 63 个；局部高度代理的帧对仍为 26，说明这组稀疏性主要不是绝对高度门槛造成。速度阈值放宽到 0.30 后多出的帧对可能是滑动脚，不能直接用于接触监督。

Crouch 候选中 181 个“低速但高于 10 cm”的帧位全部来自 `right_foot`，而非脚趾骨。以 `201` 为例，中心窗口 `right_foot` 中位高度约 15.79 cm，`right_toe` 约 3.19 cm；`208` 为 14.94 cm 与 3.30 cm。同一动作内部脚骨和脚趾骨的高度差比“整条地面平面偏移”解释更直接。它只说明当前**同一绝对高度阈值对不同骨骼不等价**；没有 UE 地面碰撞真值，不能把这 181 帧位写成漏标的物理接触。Walk 107 帧位也全在两个 foot 骨，提示相同校准问题。

先前的训练覆盖审计仍成立：0.2–1 m/s 且窗口内速度稳定的训练窗口，Walk 19、Run 2、Crouch **0**。窗口重叠且未必是独立动作；现有数据无法证明匀速慢蹲行已经受充分监督。脚速度轨迹损失的同条件续训对照也未带来稳定验证收益，因此本设计不把直接增大脚部损失当第一步。

## 新训练设计与实施顺序

1. **保留封版与基线。** 原始片段、split、Root/姿态配对和原接触位不改。建立接触标签 `v2` 的旁路诊断表：分别保留 foot/toe 原始高度、世界脚速、局部低点、相邻帧持续时间和可追溯资产/帧索引。只对少量 Run 高速片段及 Crouch/Walk 骨骼高度分歧帧做 UE 蒙皮、地面 Trace 与人工抽查，建立 `可信 / 不确定 / 排除`，不把局部高度代理直接当真值。
2. **先做数据消融。** 同一模型、同一起点、同一步数比较现有样本策略与速度/阶段分层采样；限制重复窗口权重，报告独立片段数。低质量接触位在接触相关损失中降权或屏蔽，但姿态监督继续使用可靠的 Root/姿态配对。对速度缩放增强单列实验，必须同步变换 Root、姿态时间采样及接触时间轴；慢速 Crouch 的真实性仍待新来源动作或真实 UE 录制验证。
3. **再试训练目标。** 先以可靠接触段测试接触状态/相位辅助头和按步态阶段的足端轨迹，再做骨长/FK 与接缝一致性消融；每次只加一个因素。此前全帧四脚世界速度矢量 SmoothL1 权重 `0.01` 的三轮续训未改善主要分组，不能作为默认方案。接触目标用可靠段监督，不用阈值扩张自动制造标签。
4. **固定真实推理契约。** 玩家 Stand/Crouch 状态、当前速度/转向/加速度、历史生成姿态和 CMC 可在线得到或因果预测的 Root 轨迹作为输入。CMC 负责 Actor 位移；模型输出下一段局部骨架姿态及可选接触/相位估计。训练和验证都禁止使用在线拿不到的未来真实姿态；来源未来 Root 的离线分数与真实 CMC 结果分开报告。
5. **逐级验收。** 固定验证集先比较 24 帧中心窗口、72 帧以上闭环、速度与阶段分层。至少报告脚速（有足够可靠接触帧对才计算）、姿态 RMSE、窗口接缝、骨长/脚穿地、Root 与脚步方向一致性；脚速改善不能以姿态明显退步换取。最后用 CMC Root 驱动 UE 蒙皮，观察 Walk/Run/Crouch 的起停、转弯与站蹲切换，再决定是否解锁一次冻结测试。同步保存视频与源片段、Root、模型权重哈希。

**当前决策：**从接触定义与速度分层开始做下一组可证伪消融；不切换到上次未通过的脚速度损失权重，不修改封版接触位，不声称这 30 条已有物理接触真值或 UE 玩家闭环验证通过。

## 复现与产物

```powershell
$env:PYTHONPATH=(Get-Location).Path
$py='D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe'
& $py 'docs/experiments/assets/2026-09-26-contact-review-training-design/analyze_review_queue.py' --release 'E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924' --baseline 'output/closed_loop_eval_20260925_run02/center_validation.csv' --queue 'docs/experiments/assets/2026-09-25-contact-speed-audit/result/review_queue.csv' --output 'docs/experiments/assets/2026-09-26-contact-review-training-design/result'
```

分析脚本见 [analyze_review_queue.py](assets/2026-09-26-contact-review-training-design/analyze_review_queue.py)。输出结果可重建；上面的命令会覆盖同名结果文件。方案图由图像生成工具按本记录的数字与训练决策制作，文件 SHA-256 `77834e45bd3bf757d16fe12ce22d7dec3a746a78d555445fc14e5a7119dd1018`。训练方案是待验证假设，图中的箭头不代表阶段已经完成。
