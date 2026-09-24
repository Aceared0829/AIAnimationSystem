---
name: review-motion-data
description: 在 AIAnimationSystem 中审计、可视化复核或人工验收动作数据时，使用项目既有 Motion Review 服务、骨架播放器和持久化结论；适用于 BONES-SEED 重定向批次与 prepared 条件动作数据。
---

# 项目动作数据验收

项目的人工验收入口是 `data/tools/motion_review_server.py` 和 `data/tools/review_web/`。需要支持新数据格式时，给这个入口增加数据适配，复用播放、队列、结论和导出能力；不要另建独立的 `review.html` 或浏览器本地存储结论流程。

## 选择数据模式

- BONES-SEED → UEFN 重定向批次：按 `docs/motionbricks/motion_pipeline.md` 和 `process-motion-batches` 的停批规则运行质量初筛，再用原服务验收。普通队列优先纳入异常，并固定抽样；异常分流使用 `--exception-triage`。不要将抽样通过称为全量逐条通过。
- 已准备的 Root/姿态条件数据：先有 `contract.json`、审计 `report.json` 和 `review_queue.json`，再用同一服务的 `--conditioned-contract`、`--conditioned-audit` 模式。队列按 50 条分页，来源 NPZ 加载时核对哈希。具体数据契约与复现命令见 `docs/reference-guided-data-contract-v1.md`。

两种模式的人工结论均由 Motion Review 保存到所选 `--library` 下的 `reviews/decisions.sqlite3`，并按固定名单隔离。展示和导出不修改来源动作、训练分区，也不自动入库或清理。磁盘目录可能经 Junction 指向 E 盘；报告实际保存位置时先解析路径。

## 验收边界

查看骨架播放、三维 Root 轨迹和异常帧后记录具体结论与备注；不要把轨迹高度压成地面投影，世界位移模式应展示角色真实移动，姿态跟随模式单独提供。视口交互按 UE 常用鼠标与键盘习惯保持一致。批量标记不能代表逐条观看。离线线框不能替代 UE 中的蒙皮、IK、碰撞、脚接触及场景落点验收。若验收入口无法读取新格式，先核对当前服务的适配能力和已有记录，再扩展原服务；保留哈希绑定、固定队列和 SQLite 持久化。
