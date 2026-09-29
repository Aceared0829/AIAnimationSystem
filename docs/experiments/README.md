# 实验记录

这里保存 AIAnimationSystem 数据、训练、评估、推理和 UE 验证实验的 **Git 可追溯摘要**。一次实验一份 Markdown，包含实际配置、数据身份、对照与评价口径、结果、失败和原始证据位置。新记录复制 [_template.md](_template.md)；执行细则见项目 skill [record-research-experiments](../../.agents/skills/record-research-experiments/SKILL.md)。

记录文件命名为 `YYYY-MM-DD-short-slug.md`，日期采用实验开始的本地日期。状态用“进行中 / 完成 / 失败 / 中止”，并在续跑或复核时更新修订历史。可分享的小型配置、指标报告、图表和审核导出随记录放在 `assets/<实验 ID>/` 并提交。训练权重、原始数据和大体积输出留在项目既有本地目录；记录应写出稳定标识、可访问的归档位置或重建方法及可用的哈希。路径只在作者机器上有效时须明确说明。

## 索引

已有历史结果仍保留在 [Root 驱动与硬参考姿态数据契约](../reference-guided-data-contract-v1.md)、[UE 插件与训练说明](../../unreal-script/AILocomotionSystem/README.md) 和 [跑酷参考姿态实验](../../inference/profiling/pose-reference-lab.md) 中；它们不因本索引建立而变成统一口径的对照实验。

新记录在这里新增一行，注明日期、类型、状态和主要证据：

| 日期 | 实验 | 类型 | 状态 | 主要证据 |
| --- | --- | --- | --- | --- |
| 2026-09-25 | [P0 站蹲数据与审核基线审计](2026-09-25-p0-stance-data-audit.md) | 数据审计 / 离线视觉复核 | 完成；107 条按用户决定全部通过 | 4 条逐帧图、窗口跨度、13 组家族表、[107 条确认清单](assets/2026-09-25-p0-stance-data-audit/restart_2026-09-25/review_acceptance.csv) |
