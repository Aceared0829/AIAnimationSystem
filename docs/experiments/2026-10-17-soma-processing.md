# 原生运动恢复、SOMA 观察与轻量处理试点

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-10-17-soma-processing`；离线数据保真、候选提取、审核工具验证 |
| 日期与时区 | 2026-10-17，Asia/Singapore；精确开始时间未记录 |
| 状态 | 30 条技术试点完成；全库扩量按用户后续指令不执行 |
| 执行者与来源 | 本项目脚本执行；SOMA/BONES-SEED 来源资产，非本项目采集 |
| 代码状态 | 初始 HEAD `e1f7773`，试验时 dirty；对应本 PR 原生导入、SOMA 参考、轻量处理及审核适配文件 |

## 问题与操作

恢复原生运动交换、独立导入与回读，固定 SOMA uniform 78 节点参考快照。在既有 30 条代表动作上保留来源时间、完整局部 TRS 和来源语义，生成可逆 Root 代理、三态接触候选、参考及任务候选索引，并在既有 Motion Review 页面显示。

该试点为技术审计，没有模型训练或算法对照。数值误差、文件/路径覆盖与 HTTP 回读是直接检查项；没有独立接触真值，不能报告接触准确率。旧详细 GPT 6 luna 分段流程因人工反馈不足而退役，相关历史 JSON 与截图保留，不计为通过。

## 代码、数据与生效配置

- 来源批次：`20261017_observation_pilot_v1`；来源语义批次：`20261017_semantic_review_v2`。
- 本次处理：`E:/MotionWeaverData/reports/soma_observation/20261017_processing_v1/run.json`，仅本机有效。原始/处理动作不改写。
- 元数据 SHA-256：`71d09422034946d17dbb0db027d569408c486545bdb12f7979d55e6ffd9bbc39`。
- 固定参考：`data/skeletons/soma_uniform_v1.json`；源运动有 29/1 两种骨架签名，未将参考变体伪装成已重定向结果。
- 生效规则：`soma_processing_v1`，来源声明秒数、不重采样；Hips X/Z + 有效人体 yaw，Root Y=0，全部录制高度留在身体位置。原始局部 TRS 独立保留。
- 接触阈值：进入低速 0.12 m/s，离开低速 0.25 m/s，稳定至少 0.10 s，高度范围至多 0.025 m；稳定高度聚类容差 0.04 m。非接触候选同时要求速度至少 0.50 m/s、垂直速度至少 0.15 m/s、远离稳定高度至少 0.06 m。
- 训练分区与统计量：未建立；任务索引全部 `training_ready=false`，参考全部待筛选且没有硬约束。随机种子、优化器和 GPU 不适用。
- 环境：Windows，仓库 Python 3.12 虚拟环境，NumPy/SciPy，Node；未启动 UE 或 Blender。

实际执行：

```powershell
./.venv/Scripts/python.exe -m data.tools.prepare_soma_processing --index E:/MotionWeaverData/reports/soma_observation/20261017_semantic_review_v2/export-index.csv --run-id 20261017_processing_v1
./.venv/Scripts/python.exe -m data.tools.motion_review_server --library E:/MotionWeaverData --native-index E:/MotionWeaverData/reports/soma_observation/20261017_processing_v1/export-index.csv --port 8781
```

## 结果与证据

| 检查 | 结果 | 口径与证据 |
| --- | --- | --- |
| 独立 BVH FK 对导入数据 | 最大误差约 `4.45e-15 m` | 先前 30 条来源帧保真，[观察回执](2026-10-17-soma-observation-pilot.json) |
| Root/身体位置重合成 | 最大绝对分量误差 `3.552713678800501e-15 m` | 对 30 条全部有效录制帧和全部源关节聚合；门槛 `1e-9 m` |
| 非镜像来源语义关联 | 71,132 条；动作路径无缺失 | 元数据粗索引，不代表读取或人工验收了全库动作轨道 |
| 基础语义字段非空 | 运动类型、姿态、短说明、首条自然描述无空白 | 不等于语义正确 |
| 新审核 HTTP 回读 | 30/30 | [HTTP 回执](2026-10-17-soma-processing-http.json)；检查数组长度、手部保持未知及旧模型字段不存在 |
| 历史人工备注 | 原 3 条保留，新页面读到 3 条 | 原数据库只读；新批次不继承旧结论 |
| 页面操作 | 接触区间跳至对应播放帧，切换动作及查看历史备注可用 | [审核截图](assets/2026-10-17-soma-processing/review.png)；未替用户批准样本 |

NPZ 已逐数组落盘回读相等。完整本地 `run.json` 保存输入/输出哈希、每条误差、候选比例及来源骨架签名；原始动作和大体积派生数组不提交。来源参考与人工验收分别记录，见其他同日 JSON 回执及 [处理实现](../soma-motion-processing.md)。

## CR、异常与边界

源码审查修正了 glTF 动画/skin 负编号静默选择末项，以及 GLB 块头截断可能抛出批次外异常的问题；临时目录探针均确认改为 ValueError。新文件导入排序已修正。既有导入、骨架、FK/审核、来源时间、数值特征及前端视口/预加载检查通过。

直接测得的是可逆位置表示和数据/界面功能。手部接触始终未知；脚部三态是启发式候选，多高度不是恢复了场景。Root 代理不等于真实 Actor，目标 rest 重定向、局部硬约束网络适配、蒙皮、碰撞、接触准确率与在线代理控制均未验证。

用户随后要求仅 CR、修复与合并，E 盘不扩量；没有启动七万条轨道处理任务。
