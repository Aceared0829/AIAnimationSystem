# Root 与姿态配对的 UE 四路滑步对照

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-25-root-pose-alignment`；现有数据诊断 / UE CMC / NNE 蒙皮 |
| 日期与时区 | 2026-09-25 +08:00；精确起始时间未记录 |
| 状态 | 完成；确定演示 Root 错配和模型自身滑步是两个独立问题 |
| 执行者与来源 | Codex 在 AIAnimationSystem 本机工作区执行；封版来源动作、既有微调权重、UEFN Mannequin 资产 |
| 前序记录 | [UE 内条件模型推理与蒙皮验证](2026-09-25-ue-skinned-inference.md)及其滑步复核 |

## 问题和固定条件

前一组 UE 视频将源动画历史姿态配上另一条速度/转向不同的 CMC Root，接触脚严重滑；即使使用源动画真实姿态，错配 Root 后也会滑。本次要分开检验：**同速同向的 CMC 是否恢复原动画落脚；在这种配对条件下模型是否仍滑；规划 Root 与实际 CMC 差距、UE 骨骼映射是否另添误差。**

预先从封版数据挑选三条历史/未来 96 帧内步速及 Root 方向稳定的片段：Walk `1587`（验证，0 起点，1.65 m/s）、Run `1109`（**训练**，0 起点，3.75 m/s）、Crouch `146`（验证，0 起点，2.25 m/s）。Run 验证分区没有同样稳定的 96 帧直线片段，此处只能做机制定位，不能把 Run 结果当留出集泛化成绩。Crouch 的 2.25 m/s 仅为了匹配这条来源片段，**不是推荐的玩家蹲行速度**。来源资产、分区、哈希见[夹具清单](assets/2026-09-25-root-pose-alignment/fixture_manifest.json)。没有改训练、验证或测试分区。

UE 5.8.2 `ACharacter`/CMC 测试 World 各运行 60 帧暖机和 96 帧记录，实际移动方向由所选来源 Root 初始局部方向映射，角色朝向固定；蹲行从暖机前就已获准蹲下。真实胶囊轨迹见[CMC CSV](assets/2026-09-25-root-pose-alignment/cmc_trace.csv)。之后取过去 24 帧和未来 72 帧；模型输入用同一条 CMC 实际 Root 的过去历史，未来 Root 由已执行速度在平地匀速外推 24 帧，不用来源未来姿态参考。首窗口过去姿态仍取来源片段，但来源和 CMC 的逐帧 Root 速度已对齐；后两窗口回灌模型姿态。

四路同时显示同一时刻、同一网格：

1. `source_source`：原动画姿态 + 原动画 Root，作为正常落脚基准。
2. `source_cmc`：同一原动画姿态 + 新录的匹配 CMC Root，隔离 Root 替换的影响。
3. `model_plan`：新模型姿态 + 模型看到的短时 Root 计划。
4. `model_cmc`：同一新模型姿态 + CMC 实际执行 Root，复现最终呈现。

## 代码、环境与复现

- 基线 HEAD `e07aad29773bf24dcadd98e36271d3af1894e7fe`；dirty 工作区，未提交。新/修改代码：[CMC 录制测试](../../unreal-script/AIAnimation/Source/AIAnimation/Private/AIAnimationCMCRootCaptureTests.cpp)、[UE 四路蒙皮及脚骨读回](../../unreal-script/AIAnimation/Source/AIAnimation/Private/AIAnimationConditionedSkinningTests.cpp)、[配对输入](assets/2026-09-25-root-pose-alignment/build_matched_fixtures.py)、[脚部汇总](assets/2026-09-25-root-pose-alignment/analyze_four_way.py)、[视频打包](assets/2026-09-25-root-pose-alignment/package_four_way.py)。没有改模型、数据契约或旧实验原始证据。
- 封版契约 SHA-256 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`；新模型权重 SHA-256 `d5e1176444238c243d8836bd2b8139485a2ec8e607ea4a5cdb7fb5a14a69ee5a`，ONNX SHA-256 `eee1e58ac2208058e51944809e1e13b0afded9826ff83e7f686ab2b6597fbcef`；录制 CMC CSV SHA-256 `0d0229c14ceae53e4e71e71f03d289f187d837f3bd19f541f5735b85a359142d`。Python 3.12.12、onnxruntime 1.24.4、UE 5.8.2 NNE ORT CPU；本机 CPU/RTX 4070 Laptop GPU，推理本身在 CPU。可分享的小型[统计汇总](assets/2026-09-25-root-pose-alignment/summary.json)和[UE 脚骨读回 CSV](assets/2026-09-25-root-pose-alignment/ue_bone_readback.csv)随记录保存；ONNX、二进制夹具和 864 张 UE 原始画面仅在本机 `output/`，可按输入哈希重建。
- 条件输入是匹配来源运动的匀速平地 CMC 历史与短期匀速 Root 外推，不是真实玩家连续按键、复杂转弯、斜坡或网络矫正。视频仍使用中性材质、UE BaseColor 截图；只对显示 RGB 做统一对比度处理和文字标注，未改任何关节或位移。
- CMC Root 来自真实 `ACharacter` 录制；四路蒙皮使用独立 `PoseableMesh` actor 重放这些 Root 和姿态，并非实时玩家角色的 AnimGraph 闭环。

复现入口（在本 worktree 根目录；输出目录须新建，不能覆盖本次证据）：

```powershell
$env:PYTHONPATH=(Get-Location).Path
$py='D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe'
$asset='docs/experiments/assets/2026-09-25-root-pose-alignment'
& 'D:\UE_5.8\Engine\Build\BatchFiles\Build.bat' UnrealEditor Win64 Development '-Project=D:\AILocomotonSystem\GR00T-WholeBodyControl-p0-review\output\ue_cmc_host\Host.uproject' -WaitMutex -NoHotReloadFromIDE
$env:AIANIMATION_CMC_MATCHED_TRACE_PATH=(Join-Path (Get-Location) 'output/cmc_root_steady_matched_20260925_v2.csv')
& 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' 'D:\AILocomotonSystem\GR00T-WholeBodyControl-p0-review\output\ue_cmc_host\Host.uproject' '-ExecCmds=Automation RunTests AIAnimation.Lab.SteadyCMCRootCapture' '-TestExit=Automation Test Queue Empty' -unattended -nop4 -nullrhi -stdout -FullStdOutLogOutput
& $py "$asset/build_matched_fixtures.py" --trace 'output/cmc_root_steady_matched_20260925_v2.csv' --candidate-onnx 'output/ue_skinned_inference_20260925/onnx/conditioned_pose.onnx' --output 'output/ue_root_pose_four_way_20260925/fixtures_v2'
$env:AIANIMATION_ROOT_POSE_FIXTURES=(Resolve-Path 'output/ue_root_pose_four_way_20260925/fixtures_v2').Path
$env:AIANIMATION_ROOT_POSE_CANDIDATE_ONNX=(Resolve-Path 'output/ue_skinned_inference_20260925/onnx/conditioned_pose.onnx').Path
$env:AIANIMATION_ROOT_POSE_RENDER_OUTPUT=(Join-Path (Get-Location) 'output/ue_root_pose_four_way_20260925/render_v2')
& 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' 'D:\AILocomotonSystem\GR00T-WholeBodyControl-p0-review\output\ue_cmc_host\Host.uproject' '-ExecCmds=Automation RunTests AIAnimation.Lab.RootPoseFourWay' '-TestExit=Automation Test Queue Empty' -unattended -nop4 -stdout -FullStdOutLogOutput
& $py "$asset/analyze_four_way.py" --fixtures 'output/ue_root_pose_four_way_20260925/fixtures_v2' --ue-render 'output/ue_root_pose_four_way_20260925/render_v2' --output "$asset/summary.json"
& $py "$asset/package_four_way.py" --raw-frames 'output/ue_root_pose_four_way_20260925/render_v2' --fixtures 'output/ue_root_pose_four_way_20260925/fixtures_v2' --work-frames 'output/ue_root_pose_four_way_20260925/packaged_frames' --media "$asset/media" --ue-log 'output/ue_root_pose_four_way_20260925/ue_four_way.log'
```

实际运行把两个 `-stdout` 流分别保存到 `output/ue_root_pose_four_way_20260925/steady_capture_v2.log` 和 `ue_four_way.log`。[UE 测试摘录](assets/2026-09-25-root-pose-alignment/ue_test_evidence.txt)记录目标测试 `Result={Success}`、各模型窗口数值误差及脚骨读回误差。全部录像按 15 FPS 放慢原 30 FPS 到 0.5 倍速，所有通道时间比例相同。

## 结果和可观看效果

UE 脚速取 `foot_l/ball_l/foot_r/ball_r` 四个**实际读回的世界骨骼位置**，只统计来源启发式接触标签在相邻两帧都成立的帧对，单位 m/s；接触段漂移是每段脚骨相对段首的最大位移。标签仍非真实地面碰撞真值，Run 仅有 19 个相邻接触帧对。视频底部每帧的数字也是这个 UE 读回口径。

| 场景与分区 | 来源/CMC 速度 m/s | 来源姿态+来源 Root | 来源姿态+匹配 CMC | 模型姿态+计划 Root | 模型姿态+实际 CMC | 模型接触段平均最大漂移 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Walk，验证 | 1.65 / 1.65 | 0.039 | 0.039 | 0.406 | 0.406 | 4.40 cm |
| Run，**训练** | 3.75 / 3.75 | 0.066 | 0.066 | 3.807 | 3.807 | 24.00 cm |
| Crouch，验证 | 2.25 / 2.25 | 0.065 | 0.065 | 0.790 | 0.790 | 10.98 cm |

三组逐帧来源/CMC Root 速度矢量差接近零，模型计划与 CMC Root 位置差也在报告精度内为零；四路的**上两格接近一致、下两格接近一致**正是这个对照应有的结果。UE `PoseableMesh` 世界脚骨读回与从输出位置计算的期望值最大误差为 CSV 的 0.000000 cm，两个 UE 目标自动化测试通过，模型 NNE 对 Python ORT 的 9 个窗口最大误差在日志九位小数内为零。由此，本次配对修好了**演示构造的 Root 错配**，但新模型的落脚问题依然存在；Run 这个诊断片段尤其差。完整逐案例、接触段数量、峰值漂移和窗口边界脚位移见[统计汇总](assets/2026-09-25-root-pose-alignment/summary.json)。

直接观看 UE 蒙皮四格视频：[Walk](assets/2026-09-25-root-pose-alignment/media/walk_four_way.mp4)、[Run](assets/2026-09-25-root-pose-alignment/media/run_four_way.mp4)、[Crouch](assets/2026-09-25-root-pose-alignment/media/crouch_four_way.mp4)。每段 72 帧，左上原动画+原 Root，右上原动画+匹配 CMC，左下模型+计划 Root，右下模型+实际 CMC；[媒体清单](assets/2026-09-25-root-pose-alignment/media/manifest.json)含视频哈希。人工复核末帧及抽样帧：来源两路肢体与地面关系相近；模型两路仍有脚相对地面滑动、跑步姿态尤为不稳定。观看结论只针对这三个预选片段。

## 结论与下一步

- **直接测得：**控制器速度/朝向匹配可以把原动画接触脚速恢复到约 0.04–0.07 m/s；同样条件下新模型仍为 0.41/3.81/0.79 m/s。Root 计划误差和 UE 脚骨映射不能解释这组模型滑步。先前演示的 Root 错配是真问题，却不是唯一问题。
- **工程判断：**先用现有 Walk/Run/Crouch 数据做独立片段的速度、转向和脚相位分层，优先建立可信的接触/地面标签与逐帧生成历史闭环指标，再对成对 Root+姿态做训练消融。可试接触状态预测、FK/骨长与脚部时序约束；此前把接触损失权重直接提高或用低 precision 的高度启发式锁脚已有姿态代价，不应直接作为产品修复。Root 计划在当前匀速平地已精确，下一阶段须再测真实转向/起停，不能用这个精确案例替代复杂控制验证。
- **尚未验证：**真实玩家持续控制、慢速蹲行、起停/转向、站蹲切换、地形/碰撞、网络预测，以及 Run 的留出片段泛化。Run 只用了训练分区片段，3.807 m/s 不能写成验证集或整体 Run 指标；这组实验没有新训练或 IK/脚锁定修正，也不能宣称当前模型可用。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-25 | 记录匹配速度/朝向的 CMC 测试、UE 四路视频、脚骨读回及失败样例 | 夹具与 CMC CSV、UE 测试摘录、统计与视频清单 |
