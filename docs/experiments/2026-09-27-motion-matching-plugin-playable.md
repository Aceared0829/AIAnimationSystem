# MotionMatchingInCpp 插件角色实跑与方向/轨迹审计

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-27-motion-matching-plugin-playable`；UE 玩家闭环推理、方向与脚滑诊断 |
| 时间 / 执行者 | 2026-09-27，Asia/Hong_Kong；本项目本机实测 |
| 状态 | 接线与自动操控验证完成；模型动作质量未通过 |
| 前序 | [独立 PoseableMesh 玩家探针](2026-09-27-live-player-probe.md)、[短训练负结果](2026-09-27-contact-v2-pilot.md) |

## 问题与实现

旧探针用独立 `UPoseableMeshComponent` 显示模型，未走目标插件的玩家角色、原动画蓝图及 Chooser。本次以 `MotionMatchingInCpp` 的 `APlayerCharacter`、Enhanced Input、CMC、原 `ABP_PlayerCharacter_C` 为玩家链路，在原 AnimGraph 输出前插入在线姿态节点。`1` 显示原 Motion Matching，`2` 显示对照模型，`3` 显示此前未通过的速度/相位试验模型；蹲伏、离地及无效模型姿态回退原动画。Actor 位移始终由 CMC 执行。

`MotionMatchingInCpp` 插件只在 `output/ue_cmc_host/Plugins/` 内保留实体副本，准备命令只修改这个副本中的 AnimBP。原项目 `D:/UnrealDataEngine/UrealDataEngine/Plugins/MotionMatchingInCpp/` 的源码没有参与本项目提交。桥接插件源码在 [`unreal-script/AIAnimationMotionMatching/`](../../unreal-script/AIAnimationMotionMatching/)；[`setup_motion_matching_host.ps1`](../../unreal-script/AIAnimation/Tools/setup_motion_matching_host.ps1) 和 [`launch_motion_matching_test.ps1`](../../unreal-script/AIAnimation/Tools/launch_motion_matching_test.ps1) 是当前本机入口，`play_live_test.cmd` 调用后者。需要本机已有的 Host、UE 5.8.2、准备过的 AnimBP 及模型包；不代表可直接打包发行。

用户反馈“前进时给出别的方向的动画”后，核对了四层：

1. `RootPlanInput` 原本并非空值，但未来 24 帧只是当前 CMC 速度的匀速外推；没有读取未来按键。稳定前进 200 cm/s 时，第 23 帧局部 Root 约在前方 153 cm。
2. 原 AnimGraph 的骨架 `root` 与模型的 79 骨局部姿态被混用。模型模式现在把**骨架 root** 重置到参考姿态；Actor Root 仍由 CMC 负责。插件 Mesh 的 −90° 相对朝向需要保留：两个同名 Mesh 的文件哈希不同，但实测 `root/pelvis` 参考变换相同，额外再抵消 −90° 会把人物转成侧面。
3. 原推理在角色落地前就用负 Z 速度外推未来 Root，曾出现 `future_23_local_z=-300.5 cm`。现在只在站立且着地时更新，Root 计划维持地面高度；落地或站起时重新播种，蹲伏交给原 AnimBP。切换显示模式不再无故把 24 帧历史重置为 Idle。
4. 现在按已执行 CMC 速度、最近玩家移动输入、`GetMaxSpeed()`、加减速和 CMC 转向模式预测未来 24 帧。它是**因果的控制器预测**，不是未来真实 Root。未处理坡面、碰撞后的未来修正或网络预测差异。

## 可复现条件

- 代码基点 `e07aad29773bf24dcadd98e36271d3af1894e7fe`，本轮工作树 dirty，相关改动在 `unreal-script/AIAnimation/`、`unreal-script/AIAnimationMotionMatching/`、本记录和资产目录。未提交、未推送。
- UE 5.8.2，Windows，NNE ORT CPU。UE Editor 目标编译成功。模型包 `output/playable_player_20260927/bundle/` 的 manifest 契约 SHA-256 为 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`，对照模型 ONNX SHA-256 `322944017edeacb739306ec44d35aa3e58b7851da8953ee98bd69f6ab605e910`，速度/相位模型 `207642f0bef63895f7ca9fc9b9c3aaa2c17c2380ca968f47dc98c3d0016e3654`。历史/未来各 24 帧，30 Hz，79 骨，未来姿态参考全零。
- 自动前进：`-AIAnimationAutoProbe -AIAnimationAutoProbeWalk`，第 0–2 秒原 MM、第 2–4 秒模型 1、第 4–6 秒模型 2、第 6–8 秒蹲伏回退；无 `Walk` 参数则约 5 m/s。自动方向探针：`-AIAnimationTrajectoryProbe`，0–2 秒沿世界 X 前进、2–4 秒沿世界 Y 右移、4–6 秒停步；模型 1。截图取每段中段。两种模型对照均使用同一 CMC Actor 位移，不使用来源动作未来 Root。
- 实际构建命令：`D:/UE_5.8/Engine/Build/BatchFiles/Build.bat UnrealEditor Win64 Development -Project=<本机 Host.uproject> -WaitMutex -NoHotReloadFromIDE`。运行使用 `D:/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe <Host.uproject> /Engine/Maps/Entry?game=/Script/AIAnimationMotionMatching.AIAnimationMotionMatchingGameMode -game -AIAnimationAutoProbe -AIAnimationAutoProbeWalk`，且环境变量 `AIANIMATION_PLAYABLE_BUNDLE` 指向上述 bundle。

## 结果

| 条件 | 输入 Root / CMC 直接读数 | UE 蒙皮直接读数或观察 | 结论 |
| --- | --- | --- | --- |
| 2 m/s 前进，原 MM | Actor/速度朝向 `0°` | 身体约 `10°`；低位脚水平速度中位数 `0.60 m/s` | 可作插件基线 |
| 2 m/s 前进，对照模型 | 未来第 23 帧局部 Root 约 `(+160,0,0) cm`；Actor/速度朝向 `0°` | 第 3 秒身体约 `23°`；有迈步但脚滑中位数 `2.15 m/s` | 方向比先前混合 Root 稳定，速度匹配不通过 |
| 2 m/s 前进，速度/相位试验模型 | 同样约 `(+160,0,0) cm`，未来朝向 `0°` | 第 5 秒身体约 `74°`，脚滑中位数 `2.15 m/s` | 模型输出本身偏航，不采用 |
| X 前进→Y 右移→停步 | 右移段速度约 350 cm/s 向 Y，未来 Root 局部 Y 约 `+280 cm`；停步后归零；Actor 保持 `0°`，属于插件横移模式 | 第 3 秒模型仍显示近似前跑姿态，未形成可靠横移动作 | 已收到方向轨迹，但模型没有可靠执行 |

脚速口径：读取同一角色 30 Hz 足骨世界位置，仅对相邻两帧脚骨 Z 都不高于 18 cm 的样本求水平速度；各模式去掉切换后的前 0.5 秒。它是**低脚高度代理**，不是经过地面 Trace 或人工确认的真实接触。身体方向由左右上臂骨连线与骨盆到上胸的方向叉乘估计，会受姿态影响，但足以标示本次约 74° 的明显侧向偏差。2 m/s 完整结果见[最终对比 JSON](assets/2026-09-27-motion-matching-playable/final_comparison.json)：原 MM 26 个低脚样本，模型 1 为 70 个，模型 2 为 86 个。此前“只按当前速度外推 + 切模式重播 Idle”版本的两个模型中位数约 2.04 m/s；本轮 2.15 m/s，说明步态幅度有所变化但脚滑**没有改善**，不能把画面上迈步更明显当成质量提升。

截图可直接复核：[原 MM 前进](assets/2026-09-27-motion-matching-playable/forward_original_2mps.png)、[对照模型前进](assets/2026-09-27-motion-matching-playable/forward_control_2mps.png)、[速度/相位模型偏航](assets/2026-09-27-motion-matching-playable/forward_speed_phase_2mps.png)、[右移时对照模型](assets/2026-09-27-motion-matching-playable/right_input_control_5mps.png)。[旧速度外推版本的对照模型](assets/2026-09-27-motion-matching-playable/previous_velocity_only_control_2mps.png)可观察模式切换重播 Idle 的问题。Actor/模型方向和未来 Root 数值见[前进日志摘录](assets/2026-09-27-motion-matching-playable/forward_probe_excerpt.txt)及[转向/停步日志摘录](assets/2026-09-27-motion-matching-playable/trajectory_probe_excerpt.txt)。原始[前进 CSV](assets/2026-09-27-motion-matching-playable/final_forward_probe_2mps.csv)与[方向探针 CSV](assets/2026-09-27-motion-matching-playable/intent_trajectory_probe_5mps.csv)已保存；完整 UE log 和中间版本只在本机 `output/playable_player_20260927/`；最终前进 CSV SHA-256 `0ad99cd1ef45908799390ec99f7387dfbe160776ceaea9b955f7be296a83a2ab`，方向探针 CSV `ed1004292449ac92849d5d3e5b0e5a6a1d357a03bb2060fd358b77fda9de1fac`。

## 判断与下一步

**直接测得：** 推理确实读取了历史 Root 和未来 Root 计划；原先不是“完全没给轨迹”。已修骨架 Root 混用、落地前错误竖直计划、切模式 Idle 历史重置，并加入玩家输入驱动的 CMC 未来轨迹预测。对照模型的朝向较稳定，但落脚与位移仍严重不匹配；速度/相位短训模型在直行下仍显著偏航。

**工程推断：** 目前主要阻塞已从“UE 完全没传轨迹”转为“模型闭环对轨迹的方向、速度和相位约束不足”。右移时模型继续前跑也支持这个判断，但仍需用封版验证集做输入敏感性消融，区分数据覆盖、损失、模型结构和历史分布偏移的贡献。

**尚未验证：** 手动长时间游戏、多人预测/复制、斜坡和障碍、真实接触 Trace、打包 Cook、自动修正或安全回退的姿态质量。当前模式 `2/3` 都是实验诊断，不能宣称已可替代原 Motion Matching。下一轮训练应固定本轮因果轨迹契约，按前进/横移/后退/起停与速度分层审计样本，加入方向一致性、脚步相位与可信接触评价，先离线闭环再进 UE；不再把此前负结果短训模型当候选上线版本。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-27 | 原插件角色接线、方向问题定位、Root/轨迹修正与实跑复核 | 同轨 CSV、UE log、蒙皮截图与对照 JSON |
