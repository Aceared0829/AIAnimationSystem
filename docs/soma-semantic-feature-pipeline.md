# 骨骼语义实验历史（已退役）

2026-10-17 用户确认移除详细模型验收，不再将它保留为可选工具。

已清理专用模型请求生成、返回契约、结果绑定、前端面板和相应检查。数值运动与有效朝向计算继续保留在 `data/runtime/motion_features.py`。

历史数据文件没有删除：`E:/MotionWeaverData/reports/soma_semantic_features/20261017_semantic_features_v1/` 保存两轮 GPT 6 luna 输出与执行记录，`reviews/soma_observation/20261017_semantic_review_v2/decisions.sqlite3` 保存原人工备注。新批次只读提取备注并保留原审核身份，不迁移旧通过/拒绝结论。

旧实验请求、输出和截图可以用于追溯，不代表仍有可运行的模型验收命令，也不代表语义正确率通过。当前代码、运行方式和验收范围见 [SOMA 轻量数据处理](soma-motion-processing.md)。
