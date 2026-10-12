# E 盘持续处理与异常二审

2026-10-04，Asia/Hong_Kong。本项目数据处理，无对照组。状态：二审服务已启动；此前启动被拒绝，用户再次明确要求继续后，持续监督器已于同日 16:37 启动。

用户授权技术验收后自动入库、清理对应源文件并持续处理；异常必须保留供用户二审。8 条 UE 微批、500 条待验收上限；库所在盘 44 GiB、系统盘 14 GiB 水位。真实 UE IK 重定向和训练加载器回读通过后才生成持久清理计划。

代码基线 `60f0d2b01e228636ef849259de3708cbd190f05d`，dirty 修改：`data/tools/run_overnight_seed_pipeline.py`、`motion_review_server.py`、`close_seed_batch.py`、`cleanup_seed_batch.py` 与新增二审测试。既有 UE 预览配置改动不属于本次操作。

启动命令与基线计数见 [startup.json](assets/2026-10-04-continuous-secondary-review/startup.json)。Windows、本项目 `.venv`、现有 `D:/UE_5.8` 与 `D:/GameAnimationSample`。数据正式位于 `E:/AIAnimationSystemData`；D 盘 Junction 兼容数据库旧路径。无训练、数据划分、模型指标或蒙皮质量结论。

19 项相关 unittest 通过，覆盖异常保留、隔离后排除自动发布范围、超过 50 条异常分页、追加异常保留人工结论及既有回归检查。新增异常状态 `needs_secondary_review`；通过项的混合 UE 工作目录不清理，避免影响二审数据。训练回读失败时整批保留并停止；引擎/磁盘/事务故障停止，不自动删除问题数据。

二审进程初次 PID 55076，更新后 PID 19460，地址 `http://127.0.0.1:8766`，初始 10 条异常。仅本机日志：`E:/AIAnimationSystemData/MotionDataLibrary/work/secondary_review_20261004_v2.log`、对应 `stderr.log`。数值技术验收不代表逐条人工观看，也不证明接触、朝向或视觉质量。源许可沿用既有 BONES-SEED 记录，本次不重新分发素材。

`/api/catalog` 返回 200，10 条异常；378 帧、78 骨骼的异常动作 `/api/clip` 返回 200 并成功解压。首个长动作请求在 45 秒客户端超时后中断，不能声称全部动作均已打开验证。

持续监督器启动命令被自动审批拒绝，返回 `blocked by policy`，没有细化原因。本次尚无新增入库或清理完成证据，STOP 保留。待获准启动后补充真实批次回执与清理日志；不能把测试通过写成全量处理完成。

## 同日二审拒绝与空白目标区诊断

用户明确指示当前 10 条全部不通过。数据库核对：4 条 `needs_segmentation`、6 条 `needs_skeleton_review`；全部 `output_path/output_sha256` 为空，事件仅有 `source_header_checked`。队列在执行 UE 前按超过 3000 帧与骨架头签名白名单分别隔离；不能将其归因于 UE 重定向运行失败，也不能将骨架头不匹配直接认定为源数据损坏。

通过验收服务 POST `/api/review` 为这 10 个固定 ID 保存 `rejected`，随后 GET `/api/catalog` 回读确认为 10/10。未移动或删除源文件，生产隔离状态保持。回执仅本机保存于 `E:/AIAnimationSystemData/MotionDataLibrary/reports/user_rejected_10_20261004.json`；该批量指示不代表逐条观看。

目标视口新增“尚未生成 UE 重定向输出”及分段/骨架适配原因，避免空网格误导。`node tests/test_motion_review_view.cjs` 通过，服务返回的 `/app.js` 已包含提示。浏览器旧页需刷新加载脚本。

## 同日恢复持续处理

用户完成一键加载功能确认后明确要求开始其他数据。持续监督器 PID 54292，队列 PID 47780；日志 `E:/AIAnimationSystemData/MotionDataLibrary/work/continuous_20261004_resume.log` 及对应 `.stderr.log`。已确认首个 8 条微批完成准备并进入真实 UE 重定向，目录 `work/queue_b9c1370235214bd2a77ca5709eb0bd81`。启动快照：8082 accepted_imported、1722 prepared_imported、10 needs_secondary_review、347 rejected_quarantined、133781 source_header_checked；领取后 8 retarget_running、133773 source_header_checked。C 盘 193.45 GiB、E 盘 1777.21 GiB。监督器将验收 STOP 归档后继续；保留异常和二审结论。此检查点尚未宣称新增发布或源清理完成。


## 同日 UE 批量吞吐调整

用户指出可以将多条源动作集中导入 UE 并一次 IK 批量重定向。队列原微批上限 8；尝试提高为 16 时，发现准备脚本已放宽但 UE Python 入口仍拒绝超过 8 条，UE 在创建/加载动画资产前退出。精确核对该运行的 16 条源文件均存在，未生成重定向报告或目标输出；数据库仅将这16条恢复回 `source_header_checked` 并保留失败日志。随后同步将 `run_seed_queue.py`、`prepare_soma_ue_batch.py`、`retarget_soma_batch.py` 和持续监督器上限调为32条；每批源帧总量仍限制约20000，单条导出采样预算仍为1000000，验收门槛仍为500条。当前 UE 队列已重启，首个批次25条/19922源帧进入重定向，说明帧数预算实际控制批大小。提高批量旨在摊薄 UE 启动及磁盘读写固定成本，不代表启动多个共享同一工程的 UE 进程。

调参前阶段回执 `close_96d0671dbff5e58a.json` 确认76条通过自动完整性与训练回读、正式入库并清理哈希绑定源文件，共回收约1.105 GiB；4条异常隔离为 `needs_secondary_review` 并保留源。当前库状态：`accepted_imported` 8158、`needs_secondary_review` 14、`retarget_running` 25；系统盘余量193.45 GiB、库盘余量1774.85 GiB。失败后已重启监督器 PID 41020。该批次尚未完成 UE 导出与验收；本次未运行测试。
