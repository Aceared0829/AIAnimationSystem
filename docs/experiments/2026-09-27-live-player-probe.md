# UE 玩家实时操控与条件姿态模型测试

> 本页保留最初的 `PoseableMesh` 诊断基线。当前可操作入口已经切换为 [MotionMatchingInCpp 插件角色实跑](2026-09-27-motion-matching-plugin-playable.md)；本页的 `play_live_test.cmd` 说明是当时的历史记录，旧入口需显式运行 `launch_playable_test.ps1`。

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 日期 | `2026-09-27-live-player-probe`；2026-09-27 +08:00 |
| 状态 | 可玩单机诊断窗口已编译、启动并用真实按键操作；玩家主观效果由实际操作者复核 |
| 前序 | [三臂落脚短训练与 UE 回放](2026-09-27-contact-v2-pilot.md) |
| UE | 本机 `D:\UE_5.8` 的 UE 5.8.2；`output/ue_cmc_host/Host.uproject`；NNE ORT CPU |

## 直接试玩

打开当前的 **Host** 游戏窗口；若已关闭，可在文件管理器双击 [play_live_test.cmd](../../unreal-script/AIAnimation/Tools/play_live_test.cmd)，或在本 worktree 运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\AILocomotonSystem\GR00T-WholeBodyControl-p0-review\unreal-script\AIAnimation\Tools\launch_playable_test.ps1'
```

点击游戏窗口使键盘输入生效。`WASD` 移动、鼠标或 `Q/E` 转向、按住左 `Shift` 跑、`C` 切换 CMC 蹲下、`1` 对照模型、`2` 本轮速度/阶段采样模型、`R` 重置位置和模型历史，`Esc` 或关闭窗口退出。切模型会重置 24 帧姿态历史，短暂跳变不应计入稳定行走效果；切换后至少等一秒再比较。屏幕顶部显示模型、CMC 速度、推理耗时与推理次数。窗口退出时，`output/ue_cmc_host/Saved/AIAnimation/PlayableTrace.csv` 记录每个采样点的 CMC 位移、速度、模型编号、蹲下状态及 UE 蒙皮脚骨世界位置；同名文件会被下次运行覆盖。

本窗口用于直接看现有模型失败在哪里，不保证动画姿态合理。尤其 `C` 只改变 CMC 蹲下与胶囊高度，当前 ONNX **没有 Stand/Crouch 输入**；切换时模型姿态可能完全跟不上。静止时如果看见模型身体下蹲，也是真实推理结果，不是玩家 CMC 自动切换了状态。

## 实时输入与推理路径

真实 `AAIAnimationPlayableCharacter` 接受按键，`UCharacterMovementComponent` 驱动胶囊和碰撞地板上的位移；`UPoseableMeshComponent` 只显示模型生成的 79 骨姿态，不能移动胶囊。过去 24 帧是已显示的生成姿态和 CMC 已执行 Root；启动时用**训练分区 Idle 446** 的前 24 帧作为姿态种子。每 4 个 30 Hz 采样帧重新调用一次模型，取 24 帧输出中的前 4 帧；未来 Root 仅由当前 CMC 位置/朝向及**当前速度匀速外推**。未来姿态参考全零，mask 全零；没有读取来源未来 Root、未来玩家按键或录制轨迹。实际画面将生成姿态放在本帧真实 CMC Root 上。

这是一条明确的在线基线：起停和转向时，匀速外推与实际 CMC 会有误差，正好暴露控制条件、窗口接缝与落脚问题。当前实现只针对单机平地；不包含 AnimGraph、IK、物理触地判断、斜坡、联网预测或稳定的 Stand↔Crouch 动画状态机。屏幕与 CSV 的脚位置是 UE `PoseableMesh` 读回，不等同于经物理碰撞确认的足底接触。

## 文件身份与构建

代码基点 `e07aad29773bf24dcadd98e36271d3af1894e7fe`，工作树已有其他未提交实验，本轮未提交。封版契约 SHA-256 `9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`。可玩包位于本机 `output/playable_player_20260927/bundle/`，[构建脚本](../../unreal-script/AIAnimation/Tools/build_playable_bundle.py)从训练 Idle 446、封版统计量和本轮两个 ONNX 构建它；清单记载模型、骨架、种子哈希和无未来参考约束。项目自有[角色与 GameMode 声明](../../unreal-script/AIAnimation/Source/AIAnimation/Public/AIAnimationPlayableTest.h)、[实现](../../unreal-script/AIAnimation/Source/AIAnimation/Private/AIAnimationPlayableTest.cpp)和[启动脚本](../../unreal-script/AIAnimation/Tools/launch_playable_test.ps1)是可复现入口；临时 Host 的 UE Binaries/Cache 不作为源码。

```powershell
& 'D:\UE_5.8\Engine\Build\BatchFiles\Build.bat' UnrealEditor Win64 Development '-Project=D:\AILocomotonSystem\GR00T-WholeBodyControl-p0-review\output\ue_cmc_host\Host.uproject' -WaitMutex -NoHotReloadFromIDE
```

## 本机验证与限制

UE Editor 目标编译通过。首次窗口暴露了将 WASD 当轴键绑定的 UE `AxisKey.IsAxis1D()` 断言；改为按下/松开状态后重新编译，后续启动日志显示 `AIAnimationPlayable: live CMC model test ready`，不再出现该断言。一次退出后归档的手工操作 CSV SHA-256 为 `744761cc6d72a1d609060ac468f4cda711ebd00f54b38de096c920f9082084bf`，[原始 2,145 点 CSV](assets/2026-09-27-live-player-probe/interactive_validation_trace.csv)；[汇总](assets/2026-09-27-live-player-probe/validation_summary.json)记录：2,145 个 30 Hz 采样点，其中对照模型 920、速度/阶段模型 1,225；CMC 移动帧 1,394，最高水平速度 375 cm/s，X/Y 范围分别 21.1/44.1 m；记录中的最大同步推理时间 3.65 ms。这确认按键驱动 CMC 位移、切模型和连续推理确实执行，**不等于动画质量过关**。

随后把地板与灯改为可移动光照、调整相机和窗口尺寸；最终二次编译通过，游戏窗口启动，日志再次显示模型就绪，窗口当前可供人工试玩。这些视觉改动未改输入、模型或推理口径。玩家操控序列并非固定基准，若要比较某个动作，应在两个模型下用同样按键节奏重新试，并保存 CSV/视频。模型没有接受独立的 Stand/Crouch 状态，不能用此窗口声称站蹲能力已经完成。

## 修订历史

- 2026-09-27：建立可玩 CMC + NNE 单机测试；修正键盘输入断言；验证连续按键、模型切换、CMC 位移、日志与脚骨记录；调整测试窗口照明和相机。
