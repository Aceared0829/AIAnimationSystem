---
name: process-motion-batches
description: 处理本项目 BONES-SEED 到 UEFN 的 UE 重定向、每 500 条停批人工验收、入库和安全清理工作流。
---

# 动作批次处理

代码在 `motionbricks/scripts`，数据库在 `D:/MotionDataLibrary`，源在 `D:/BONES-SEED`。使用 `D:/GameAnimationSample` 和 `D:/UE_5.8`。既有示例项目与 1722 条旧训练数据不属于清理对象。

## 固定工作流

- 真实 UE IK 重定向后导出，共享骨骼配 N 条动作；不能把源 FK 转换称为 UE 重定向。
- 每累计 500 条待验收动作停止领取。UE 微批仍最多 8 条，最后一批按剩余名额缩小。达到 C 盘 14 GiB / D 盘 44 GiB 提前停止线时，不等满 500；检查当前批次后生成验收队列。不能自动移除 `work/STOP`。
- `screen_pending_quality.py` 初筛全部待验收动作；`motion_review_server.py` 展示全部异常及其余固定随机 5%（向上取整）。名单和文件身份必须绑定，刷新不能重新抽样。
- 用户结论在 `reviews/decisions.sqlite3`。用 `record_motion_review.py --cohort <文件>` 将有哈希约束的人工结论回执存档。未标记、拒绝、待定均不能算通过；一键通过不代表逐条观看。抽样通过不是所有动作逐条人工通过。
- 人工通过不覆盖完整性错误，也不自动解除根朝向、接触、训练读取等技术门禁。入库前核验实际输出和骨骼哈希、形状、坐标约定、可用训练加载路径及持久数据库事务。未实现的发布/清理不能宣称已经完成。
- 只有逐条最终输出可回读、数据库事务落盘且来源绑定可验证后，才可清理对应源文件和 UE 中间产物。使用持久删除清单和恢复日志；路径必须逐个解析限定边界。`soma_proportional` 是指向 C 盘的 junction，需要验证物理路径。禁止递归删除源根目录、项目根目录或共享骨骼。
- 修复动作需重新导出、检查和验收，旧人工记录不能批准变化后的输出。每批结案后重新核对磁盘余量再恢复下一批。

## 现有命令与状态

仓库根目录使用 `.venv/Scripts/python.exe`。`run_seed_queue.py` 有 500 条待验收上限和磁盘门禁；`retargeted_pending_quality` 不是训练就绪。`record_motion_review.py` 仅存档人工结论，不发布、不删除。详细管线说明见仓库 `motionbricks/docs/motion_pipeline.md`。本 skill 不能代替代码验证，也不能授予超出用户请求的删除权限。
