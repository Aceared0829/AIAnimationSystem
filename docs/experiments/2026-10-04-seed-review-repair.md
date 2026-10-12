# 10 条拒绝动作的完整片段重定向修复

2026-10-04，Asia/Hong_Kong。本项目 UE 数据处理试验，无对照组。状态：重定向与完整性检查完成，等待用户二审；未入库或清理。用户要求修复上一批 10 条失败动作，并明确优先提高帧数支持、保持完整片段。

## 原因、改动与边界

4 条长动作在 UE 前因队列 3000 帧限制被拦截；此前导出器每片段最多 250000 个骨骼采样，另有配置 `MaxFramesPerClip`。这不是 UE IK 的分段要求。本次原生导出器增加命令行 `AILocomotionMaxBoneSamples`，默认 250000，允许范围 250000..4000000，并用 int64 检查帧数乘骨骼数。此次运行预算为 1000000，帧数预算 6000；队列默认提高至 6000，CLI 允许 2..12000。帧率仍为 120 FPS，不截断、不分段、不重采样。

6 条动作拥有相同的 78 个骨骼名称及父子层级，骨架头签名差异包括参考 OFFSET。身体骨骼最大偏移差 0.1501932893 cm；Hips 具有绝对平移通道，其 OFFSET 差异不能作为身体比例差处理。仅对结构一致、身体偏移差不超过 0.25 cm 且身体没有动态平移通道的动作，显式统一身体参考偏移；原绝对 Hips 平移、Root 运动和各骨骼旋转保留。该步骤是源参考归一化，最终 UEFN 重定向仍由 UE `IKRetargetBatchOperation` 执行。

重跑只使用固定 10 个 ID 和原源文件 SHA-256，不领取剩余动作，不移除全局 STOP。两次微批分别 4、6 条，采用新 `TargetRepair` 输出。成功后保存 `needs_secondary_review`，不使用旧拒绝结论批准新输出。

## 代码与执行

基线 `60f0d2b01e228636ef849259de3708cbd190f05d`，dirty 工作区。相关文件与 SHA-256 见 [configuration.json](assets/2026-10-04-seed-review-repair/configuration.json)：导出器、`prepare_soma_ue_batch.py`、`run_seed_queue.py`、`retry_seed_review_batch.py`、`screen_pending_quality.py`；验收服务与 UI 另有本会话修改。既有 UE 预览项目配置改动不属于本次操作。

```text
D:/UE_5.8/Engine/Build/BatchFiles/Build.bat GameAnimationSampleEditor Win64 Development -Project=D:/GameAnimationSample/GameAnimationSample.uproject -WaitMutex -NoHotReload -Module=AILocomotionDatasetEditor
.venv/Scripts/python.exe -u data/tools/retry_seed_review_batch.py --cohort E:/AIAnimationSystemData/MotionDataLibrary/reviews/secondary_review_live_p01.json
```

导出插件已在 `D:/GameAnimationSample/Plugins/AILocomotionDataset` 本机编译，Succeeded，42.32 秒。部署前源码备份保存在本机 `E:/AIAnimationSystemData/MotionDataLibrary/reports/repair10_20261004_exporter_before.cpp`。

首次重跑因示例项目中缺少 `MotionWeaverCMCPreview` 编译模块，在 UE 初始化时失败；没有执行重定向。随后仅在批处理命令行使用 `-DisablePlugins=MotionWeaverCMCPreview,AIAnimation`，不改项目插件配置。失败日志保留于本机 `work/queue_repair_8e1ef4e34fb04d33831eaac069f48f4d/retarget.log`。

## 结果与证据

10 条共 21727 帧，逐条与原始帧数一致。长动作完整导出 3370、3560、5135、5541 帧。最终数组包含 79 个非虚拟目标骨骼；源文件全部保留。所有输出 SHA-256、原始源文件 SHA-256、四元数/有限值/数组形状与导出审计绑定均核验。25 项 Python 检查和 Motion Review JS 回归通过。

全部 10 条通过完整性检查；2 条坐姿动作被几何初筛标记 `possible_ground_penetration`：

- `sitting_legs_cross_arm_side_loop_004__A248`，最低足部点约 -4.1795 cm。
- `sitting_legs_cross_arms_front_start_002__A188`，最低足部点约 -3.2871 cm。

这只是疑似地面穿透，仍须人工场景语义判断。全部新输出进入二审，没有以数值检查伪造人工批准。旧名单 `secondary_review_live_p01.json` 的 10 条 rejected 原样保留；新名单 `exception_triage_4e28704d9e810896_p01.json` 的结论为未验收。

小型可分享证据：[修复回执](assets/2026-10-04-seed-review-repair/repair_receipt.json)、[初筛结果](assets/2026-10-04-seed-review-repair/quality_screen.json)、[最长动作页面截图](assets/2026-10-04-seed-review-repair/5541-frame-review.png)。原始 BVH、UE 资产和完整导出均保留在本机，不重新分发源素材。

本机运行记录：`E:/AIAnimationSystemData/MotionDataLibrary/work/repair10_e9030fdf357c421cae19b19769139c69/complete.json`。两批工作路径分别为 `work/queue_repair_991068b94f18449fa9aef982cf234517`、`work/queue_repair_caf35bdafa9c403aa3f4b3baa885ca2d`，包含独立导入、重定向、导出和审计回执。源与输出身份在 [修复回执](assets/2026-10-04-seed-review-repair/repair_receipt.json) 中逐条绑定。

验收服务 `http://127.0.0.1:8766`，更新后 PID 76576。已刷新用户当前页面，真实 UI 显示最长片段完整 5541 帧、源 78 骨骼、目标 79 骨骼。另通过 API 验证 378 帧归一化动作可读取目标骨架及源参考修正说明。未声明逐条人工观看，也未证明 UE 蒙皮、接触、碰撞、训练留出划分或模型质量。
