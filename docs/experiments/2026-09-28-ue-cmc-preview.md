# UE 单机 CMC 站蹲与执行 Root 观测演示

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-28-ue-cmc-preview`；UE 单机功能与碰撞场景验证 |
| 时间 | 2026-09-28 约 18:45–19:05，Asia/Hong_Kong；最终 run `cmc_preview_20260928T110529Z` |
| 状态 | 完成：独立关卡、UE 5.8.2 构建、资产重载及自动场景通过；玩家手动试玩尚未验收 |
| 执行者与来源 | 本项目试验插件；角色、动作和环境底图取自本机 Epic Game Animation Sample；不属于 MotionWeaver 模型动画输出 |
| 前序 | [站蹲离线条件试验](2026-09-28-stance-transition-v2.md) |

## 问题与方案

问题是能否在真实 UE CharacterMovementComponent 下区分“希望站起”和“胶囊体实际能站起”，并同时观测已执行 Actor Root，而不让模型或 Mesh 再执行第二次世界位移。本轮只验证这一条单机输入/碰撞边界；不比较动画模型质量。

新增独立的 `unreal-sample/MotionWeaverCMCPreview` 实验插件。以 `D:/GameAnimationSample` 为本机宿主，复制 `/Game/Levels/DefaultLevel` 和 `GM_Sandbox` 到插件内容，副本的默认 Pawn 指向现有 `SandboxCharacter_CMC`。新地图放置低矮立方体顶棚及 `AMotionWeaverCMCTraceActor`；原地图、原 GameMode、原 `AIAnimation` 推理插件均不修改。该 Actor 只读 `bWantsToCrouch`、`IsCrouched()`、Actor Root 与速度；青线绘制已执行 Root，紫线用**当前速度 × 0.75 秒**外推，是在线可得的诊断估计，**不是 CMC 的真实未来轨迹或 Model Root 预测**。姿态仍由 GASP 样例动画生成，没有加载 B1 权重。

自动场景依次蹲下、沿 +X 走入顶棚、请求站起并等待、继续离开顶棚、再次确认站立。接受条件为顶棚下持续保持实际蹲伏，离开后实际站立；同时生成含时间戳的 CSV 和两张游戏内截图。头顶碰撞由 CMC 处理，观测器不改胶囊体或位移。

## 代码、环境与数据

- 仓库基线 `e07aad29773bf24dcadd98e36271d3af1894e7fe`；本轮试验使用未提交工作树，相关变更为 `unreal-sample/MotionWeaverCMCPreview/`、`unreal-sample/create_cmc_preview.py`、`unreal-sample/verify_cmc_preview.py` 与本记录。仓库中另有前轮站蹲训练试验的未提交文件，本轮未清理或覆盖。
- 宿主 `D:/GameAnimationSample/GameAnimationSample.uproject`，UE 5.8.2；插件以 junction 挂在宿主 `Plugins/MotionWeaverCMCPreview`，实际源码在当前工作树。GASP 原角色与 Content 未搬入仓库。
- 生成的 `/MotionWeaverCMCPreview/Maps/L_CMCPreview` 和 `/MotionWeaverCMCPreview/Blueprints/BP_GM_CMCPreview` 仅在本机插件 `Content` 中；仓库规则忽略 `unreal-sample/**/Content/`。分别 SHA-256 为 `9533455a63a69a68092890ed4f9d2cbc477158983de3a77cf86a6b4372eb4514` 和 `9290420e7deed74e26cf3e76ac0275bab8746f0c537b84d7d1320a06b871a424`；其他机器需有合法 GASP 资产并运行创建脚本，不将本地 `.umap/.uasset` 当作可公开分发资产包。
- 观测 CSV 最多 18000 行，名义每 1/30 秒尝试一次，每个游戏 Tick 最多采一帧；**低帧率时不补帧，不能直接当固定 30 Hz 训练输入**。`cmc_wants_crouch` 是 CMC 内部期望状态，不是原始玩家按键事件；`accepted_crouch` 为 `ACharacter::IsCrouched()`。无 train/validation/test 划分，所有采样来自同一自动场景。

实际执行命令要点：

```powershell
& 'D:\UE_5.8\Engine\Build\BatchFiles\Build.bat' GameAnimationSampleEditor Win64 Development '-Project=D:\GameAnimationSample\GameAnimationSample.uproject' -WaitMutex -NoHotReloadFromIDE
& 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' 'D:\GameAnimationSample\GameAnimationSample.uproject' -run=pythonscript '-script=C:\Users\zzn19\.codex\worktrees\motionweaver-stance-root\GR00T-WholeBodyControl\unreal-sample\create_cmc_preview.py' -unattended -nop4 -NullRHI -NoSplash
& 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' 'D:\GameAnimationSample\GameAnimationSample.uproject' -run=pythonscript '-script=C:\Users\zzn19\.codex\worktrees\motionweaver-stance-root\GR00T-WholeBodyControl\unreal-sample\verify_cmc_preview.py' -unattended -nop4 -NullRHI -NoSplash
& 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe' 'D:\GameAnimationSample\GameAnimationSample.uproject' /MotionWeaverCMCPreview/Maps/L_CMCPreview -game -windowed -ResX=1280 -ResY=720 -NoSplash -MotionWeaverAutoTest
```

## 结果与证据

| 项目 | 实测结果 | 口径与证据 |
| --- | --- | --- |
| UE 编译 | `GameAnimationSampleEditor` / `MotionWeaverCMCPreview` 编译和链接成功 | 最终 5/5 UBT action，`Result: Succeeded` |
| 资产重载 | 目标地图为副本 GameMode，默认 Pawn 为 `SandboxCharacter_CMC`；观测器和顶棚各 1 个 | `verify_cmc_preview.py`：0 error、0 warning，日志 `MW_VERIFY` |
| 站蹲碰撞 | 自动测试 `MW_CMC_AUTO_TEST_PASS`；请求站立但仍蹲伏的采样 39/119，时间 2.0363–3.7731 秒；离开后首个站立采样 Root X = −315.925 cm | [最终 CSV](assets/2026-09-28-ue-cmc-preview/cmc_preview_20260928T110529Z.csv) 与[小型摘要](assets/2026-09-28-ue-cmc-preview/summary.json)；这是一次场景验证，不是统计泛化指标 |
| 视觉复核 | 侧视截图中顶棚下为蹲姿且 HUD 为 `CMC wants: STAND / Actual: CROUCH`；离开后 HUD 与身体均为站立 | 本机 `D:/GameAnimationSample/Saved/MotionWeaver/cmc_blocked_20260928T110526Z.png`、`cmc_standing_20260928T110529Z.png`；SHA-256 见摘要 |

最终 CSV SHA-256 为 `e8ae6f63c7e36979bb3e1ae6ec13bf6694b66ae0ab91ffca32e50f93a9516c14`，仓库内副本与本机 `Saved/MotionWeaver` 原始文件一致。截图为 GASP 内容派生画面，留在本机，未复制到 Git。首次自动运行的第三人称相机进入顶棚，角色不可见；改为**仅自动测试使用**的侧视相机后重跑并保留最终截图。游戏启动日志还包含 GASP 样例若干 Editor Utility Widget 的 Blueprint 编译错误；本轮未修改这些资产，特定 CMC 场景仍完成，不能据此声称整个样例工程无错误。

## 结论与使用边界

- **直接测得：**在此本机 GASP 关卡中，CMC 的期望站立与实际蹲伏可分开观测；低矮顶棚阻止起身，离开后可以站立；Actor Root 轨迹和非固定间隔状态采样可记录。
- **工程推断：**这张地图可作为下一阶段实时条件模型的单机碰撞/状态夹具，但需要先记录真实玩家输入、构造可在线取得的短时 Root 计划、把非固定采样重采样到训练时间网格，并把连续生成姿态接回当前角色。
- **尚未验证：**手动键鼠试玩、模型驱动姿态、Pose Token、Model Root/Mover 模式、脚部接触/IK、推理性能、联机预测/回滚及多人同步。不能把 GASP 原动画和速度外推紫线称作 MotionWeaver 生成结果。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-28 | 首次建立单机 CMC 独立插件、地图及自动场景记录 | UBT、UE 资产重载、最终日志、CSV 和两张人工复核截图 |
