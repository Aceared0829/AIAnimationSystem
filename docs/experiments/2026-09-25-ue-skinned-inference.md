# UE 内条件模型推理与蒙皮验证

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-25-ue-skinned-inference`；UE 推理 / 蒙皮视觉验证 |
| 日期与时区 | 2026-09-25 +08:00；精确开始时间未记录 |
| 状态 | 完成；隔离的 UE 测试 World 通过，玩家实时闭环仍未通过 |
| 执行者与来源 | Codex 在 AIAnimationSystem 本机工作区执行；使用项目现有数据及既有/新微调权重、UEFN Mannequin 资产 |
| 前序记录 | [无参考连续推理、脚部约束与 UE CMC Root 联合实验](2026-09-25-closed-loop-optimization.md) |

## 问题与方案

上一轮视频只有 Python 骨架和 UE CMC 轨迹，无法检验模型能否在 UE 内执行，也看不到真正网格变形。本次在 UE 5.8.2 的自动化 `Game` 测试 World 中，使用 NNE 的 ORT CPU 后端执行旧 `uniform12` 与新 `generated_contact10` 两个模型，并把 79 骨骼姿态写入原版 UEFN Mannequin 的 `UPoseableMeshComponent`。同一帧的左侧为旧模型、右侧为新模型。

四组固定片段为 Walk、Run、已有蹲姿历史继续 Crouch，以及 Walk 站立历史接 CMC 已接受蹲下请求。每组 72 帧、30 Hz、3 个连续 24 帧窗口。首窗口以来源动作的过去 24 帧暖机；输入的当前控制保持 24 帧 Root 计划是**因果代理**，后续窗口历史由对应模型生成姿态回灌；姿态参考全为零、mask 全为零。UE 中用已录制 CMC 胶囊底部 Root 放置角色，以隔离并观察姿态。该实验没有实时玩家输入、AnimGraph、脚 IK 或游戏中的完整姿态管线。

## 代码、环境与数据

- 基线提交：`e07aad29773bf24dcadd98e36271d3af1894e7fe`；实验在未提交工作区完成。相关新增代码：[ONNX 导出](assets/2026-09-25-ue-skinned-inference/export_conditioned_onnx.py)、[输入构建](assets/2026-09-25-ue-skinned-inference/build_cmc_fixtures.py)、[UE 测试](../../unreal-script/AIAnimation/Source/AIAnimation/Private/AIAnimationConditionedSkinningTests.cpp)、[视频打包](assets/2026-09-25-ue-skinned-inference/package_ue_videos.py)。本实验未重新训练。
- 数据契约 SHA-256 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`；79 骨骼、30 FPS；骨架 SHA-256 `1a799ca14585ce18edcfce3bb755dc7adcffa84d5111ac3afa2aa71238b8b547`。CMC 轨迹 SHA-256 `9180776b198a0c1a5d03508fb9e69a914086f13da251bb7a5afe12e72df26fb6`。完整场景及输入文件哈希见[输入清单](assets/2026-09-25-ue-skinned-inference/fixture_manifest.json)。四条用于定点诊断，不能代表 176 段冻结测试总体。来源数据按既有封版读取，未改分区或审核结果。
- 原始权重 SHA-256：旧 `28662ffd1855ab18fc8091f866252d1800bbd2a2595222b907009891f0eb3930`，新 `d5e1176444238c243d8836bd2b8139485a2ec8e607ea4a5cdb7fb5a14a69ee5a`。导出的 ONNX SHA-256 分别为旧 `c60376116a9e8fe3e3c2e0df8460dfa50f1818eeab5986dcbee84d150bd5a178`、新 `eee1e58ac2208058e51944809e1e13b0afded9826ff83e7f686ab2b6597fbcef`。ONNX 固定输入为 `history [1,24,718]`、`root_plan [1,24,7]`、`reference [1,24,711]`、`mask [1,24,1]`，输出 `pose [1,24,711]`。见[旧模型导出清单](assets/2026-09-25-ue-skinned-inference/baseline_onnx_manifest.json)和[新模型导出清单](assets/2026-09-25-ue-skinned-inference/candidate_onnx_manifest.json)。
- Python 3.12.12、PyTorch 2.14.0+cu130、onnxruntime 1.24.4；UE 5.8.2，`NNERuntimeORTCpu`。本次没有使用远程 GPU。测试宿主 `output/ue_cmc_host/Host.uproject` 和 ONNX、二进制输入、UE 原始 PNG 均只保留在本机工作区 `output/ue_skinned_inference_20260925/`；宿主的 `Content/Characters` 指向本机 `D:\GameAnimationSample\Content\Characters` 中的 UEFN Mannequin。
- 坐标契约按封版数据 `data=(−UE Y, UE Z, UE X)`；CMC Root 用胶囊底部，不用胶囊中心。准备本实验时发现前一版 CMC 骨架对照把 UE Y 的符号写反，已经修正、重跑 `run03` 并重渲视频；前一版横向方向不可引用。

复现命令要在本机对应数据、资产和工作区齐备后，于该 worktree 根目录执行；输出目录须不存在：

```powershell
$env:PYTHONPATH=(Get-Location).Path
$py='D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe'
$asset='docs/experiments/assets/2026-09-25-ue-skinned-inference'
& $py "$asset/export_conditioned_onnx.py" --checkpoint 'E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_uniform12\epoch_012.pt' --output 'output/ue_skinned_inference_20260925/onnx_baseline'
& $py "$asset/export_conditioned_onnx.py" --checkpoint 'E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_closed_loop_ablation02\generated_contact\epoch_010.pt' --output 'output/ue_skinned_inference_20260925/onnx'
& $py "$asset/build_cmc_fixtures.py" --trace 'output/cmc_root_capture_20260925_v2.csv' --baseline-onnx 'output/ue_skinned_inference_20260925/onnx_baseline/conditioned_pose.onnx' --candidate-onnx 'output/ue_skinned_inference_20260925/onnx/conditioned_pose.onnx' --output 'output/ue_skinned_inference_20260925/fixtures'
& 'D:\UE_5.8\Engine\Build\BatchFiles\Build.bat' UnrealEditor Win64 Development '-Project=D:\AILocomotonSystem\GR00T-WholeBodyControl-p0-review\output\ue_cmc_host\Host.uproject' -WaitMutex -NoHotReloadFromIDE -gather
$env:AIANIMATION_CONDITIONED_FIXTURES=(Resolve-Path 'output/ue_skinned_inference_20260925/fixtures').Path
$env:AIANIMATION_CONDITIONED_BASELINE_ONNX=(Resolve-Path 'output/ue_skinned_inference_20260925/onnx_baseline/conditioned_pose.onnx').Path
$env:AIANIMATION_CONDITIONED_CANDIDATE_ONNX=(Resolve-Path 'output/ue_skinned_inference_20260925/onnx/conditioned_pose.onnx').Path
$env:AIANIMATION_CONDITIONED_RENDER_OUTPUT=(Join-Path (Get-Location) 'output/ue_skinned_inference_20260925/render_final')
$env:AIANIMATION_CONDITIONED_SCENARIOS='walk,run,crouch,stand_to_crouch'
$env:AIANIMATION_CONDITIONED_MAX_FRAMES='72'
& 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' 'output/ue_cmc_host/Host.uproject' '-ExecCmds=Automation RunTests AIAnimation.Lab.ConditionedSkinning' '-TestExit=Automation Test Queue Empty' -unattended -nop4
& $py "$asset/package_ue_videos.py" --raw-frames 'output/ue_skinned_inference_20260925/render_final' --work-frames 'output/ue_skinned_inference_20260925/packaged_frames' --media "$asset/media" --ue-log 'output/ue_skinned_inference_20260925/ue_render_final.log'
```

以上命令表示入口和生效参数；最终运行实际指定了 UE 日志文件 `output/ue_skinned_inference_20260925/ue_render_final.log`。已存在的输出目录需选新 run ID；请勿覆盖本次证据。`-gather` 用于首次发现新增 C++ 测试源。视频以 15 FPS 播放 72 帧，即原 30 FPS 动作的 0.5 倍速。

## 结果与直接可看的效果

| 检查 | 旧模型 | 新模型 | 口径与证据 |
| --- | ---: | ---: | --- |
| PyTorch 对导出 ONNX 的最大绝对误差 | `1.246e-5` | `4.768e-6` | 各 3 组固定合成输入；两份导出清单 |
| UE NNE 对 Python ORT 的最大绝对误差 | `0`（日志 9 位小数） | `0`（日志 9 位小数） | 四场景 × 三窗口 × 17,064 输出浮点数；[UE 测试摘录](assets/2026-09-25-ue-skinned-inference/ue_test_evidence.txt) |
| UE 蒙皮帧 | 4 × 72 | 4 × 72 | 同一场景左右对照；目标自动化测试 `Result={Success}`；[视频清单](assets/2026-09-25-ue-skinned-inference/media/manifest.json) |

可直接播放：[Walk](assets/2026-09-25-ue-skinned-inference/media/walk_ue_skinned.mp4)、[Run](assets/2026-09-25-ue-skinned-inference/media/run_ue_skinned.mp4)、[Crouch](assets/2026-09-25-ue-skinned-inference/media/crouch_ue_skinned.mp4)、[站立接蹲下请求](assets/2026-09-25-ue-skinned-inference/media/stand_to_crouch_ue_skinned.mp4)。左旧右新，均是 UE NNE 推理后的真实 UEFN Mannequin 网格，不是 Python 画出的骨架。画面使用中性 UE 材质和 SceneCapture 的 BaseColor；打包时对所有帧统一做 `clamp((RGB−4)×6,0,255)` 的**仅显示用途**对比度调整及文字标注，未改骨骼或位移。

人工复核四段视频及末帧：两模型均能驱动完整人物网格，Walk/Run 没有明显骨架拓扑错接或身体爆炸；Run/Crouch 的新模型姿态与旧模型有可见差异，但这四段视觉样例不足以断言总体质量变好，也没有实地足部接触测量。Crouch 场景从蹲姿历史开始，两模型都保持蹲姿。**站立接蹲下请求场景中，CMC 已接受蹲下 48 帧，但两模型仍基本站着**：当前模型没有显式 Stand/Crouch 条件，Root 变化本身不能产生可靠的站蹲切换。视频中的脚与地面关系仍需修正；本次未做 IK、地面查询或碰撞验证。

### 滑步复核：姿态与位移的条件不匹配

用户指出蒙皮视频严重滑步后，重读同一冻结来源片段、输入夹具和 UE 渲染实现；按 `apply_authoritative_root` 将脚/脚掌位置与不同 Root 组合。下表的脚速取**原片段启发式接触标签在相邻两帧均为接触**的帧对，单位 m/s，30 Hz；它用于对照原动作的步态相位，**不是 CMC 场景的真实物理接触测量**。Root 速度取各 72 帧轨迹的水平逐帧平均；预测 Root 误差取 72 帧与实际 CMC Root 的位置距离均值。

| 视频场景 | 来源→CMC Root 平均速度 m/s | 预测 Root 平均误差 cm | 来源姿态+来源 Root 脚速 | 来源姿态+CMC Root 脚速 | 旧模型+CMC Root 脚速 | 新模型+CMC Root 脚速 | 接触帧对 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Walk | 1.70→0.93 | 1.78 | 0.042 | 1.595 | 1.425 | 1.233 | 69 |
| Run | 3.43→2.66 | 20.12 | 0.078 | 2.304 | 3.911 | 3.958 | 13 |
| Crouch | 2.04→0.53 | 0.61 | 0.050 | 2.491 | 1.114 | 0.794 | 69 |
| Stand→Crouch | 1.70→0.53 | 0.61 | 0.042 | 1.626 | 1.108 | 0.805 | 69 |

直接证据：即使使用**原动画的完整真实姿态**，把它的 Root 换成较慢、不同方向的 CMC Root 后，原本接近静止的接触脚也产生 1.6–2.5 m/s 的世界速度。来源与 CMC 每帧水平速度**矢量**的平均差值在 Walk/Run/Crouch 分别为 1.91/4.19/2.25 m/s；Run 的均速接近并不表示运动方向一致。Walk/Crouch 的预测 Root 与实际 CMC 平均仅差 1.78/0.61 cm，但新模型脚速仍达 1.23/0.79 m/s；因此不能只归咎于轨迹预测。首窗口还把**源动画过去姿态**和**CMC 已执行的过去 Root**拼成历史，两者步速不配套。训练及接触损失见到的则是原动画未来 Root；新模型对真实控制速度的补偿虽在个别场景可见，仍不足以稳脚。Run 的标签只有 13 对，单例脚速不得外推到整个 Run 类别。

Run 另有独立问题：第二窗口末预测 Root 离 CMC 实际位置 39.92 cm；下一窗口预测重新从实际 CMC 历史起算，拼接的预测路径跨一帧跳约 50.1 cm，而显示的 CMC Root 那一帧只走 5.2 cm。模型输入因此在窗口边界失去连续性，但这个问题解释不了 Walk/Crouch 中同样严重的滑步。视频按 15 FPS 放慢了原 30 FPS 帧序列，姿态和位移同时放慢，播放倍率不是空间错配的成因。UE NNE 输出与 Python ORT 一致、坐标与米/厘米换算有明确契约；仍需单独读取 UE 实际蒙皮脚骨世界坐标才能完全排除渲染侧附加误差。

下一次验证先使用**同一条来源 Root+姿态**建立无滑步显示基准，再逐项换成匹配速度的 CMC Root、模型姿态和因果 Root 计划；记录每帧 Root、步速、朝向、左右脚相位、接触脚世界位移和两个窗口边界。初始历史也必须是同一执行轨迹上的姿态/Root 配对。对于现有数据，先按速度、转向、蹲姿筛选相容片段或同步重定时 Root 与姿态；不能只替换 Root 而保留原姿态作为训练真值。然后处理连续短时 Root 规划与模型速度/步态条件，最后在可信接触识别和完整 FK/蒙皮检查后评估落脚约束及 IK。当前项目的因果接触启发式 precision 仍不足，不宜直接开启脚锁定。

## 结论与使用边界

- **直接测得：**本机 UE 5.8.2 NNE CPU 可加载这两份 ONNX，并在四种准备好的 CMC 条件输入上得到与 Python ORT 一致的输出；79 骨骼结果可驱动 UEFN Mannequin 蒙皮并生成连续画面。选中 UE 自动化测试通过。
- **工程判断：**UE 内输出契约及蒙皮适配可以继续开发，但尚未到“玩家实时可用”。优先补在线可得的 Root 规划、Stand/Crouch 请求及 CMC 已接受状态条件和站蹲过渡样本，再解决脚部接触与窗口接缝；继续用 UE 网格视频复核。
- **尚未验证：**实时玩家输入驱动的每帧推理、AnimGraph 集成、线程/延迟与内存预算、网络预测/纠正、真实地形和物理接触、跨任意片段的稳定性。本次 NNE 延迟日志约 1–3 ms/24 帧窗口，首调用约 7 ms，但来自隔离测试，不能当游戏帧耗时承诺。
- **归属边界：**这是现有模型的导出、UE 测试和可视化适配，不是新的训练结果；模型/UEFN 网格的原始成果与本次工程验证分开记录。视频与小型报告在仓库中，ONNX、二进制输入及 UE 原始 PNG 仅在本机输出目录，可按清单哈希和上述入口重建。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-25 | 首次记录 ONNX 导出、UE NNE 数值对照及四段蒙皮视频 | 导出/输入清单、UE 测试摘录、视频清单和人工复核 |
| 2026-09-25 | 用户指出严重滑步后，复核来源/CMC 步速、Root 计划和接触脚速度，列出原因与验证顺序 | 冻结来源、四组输入夹具、模型输出和 CMC 轨迹；仅做只读计算，未改模型或视频 |
