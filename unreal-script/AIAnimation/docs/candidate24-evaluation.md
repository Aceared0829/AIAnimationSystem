# 24 帧稀疏条件推理实验（2026-09-22）

候选方案保持 relative_v2 权重、30 Hz 采样、4 帧推理步长和 8 帧播放延迟。只将历史窗口改为 24 帧，并把窗口首尾已知源姿态作为解码器软条件。未做末端速度外推、直接纠正骨盆位置、重训练或手脚硬约束。

这是已知动画重建实验，额外使用的姿态条件不能当作玩家意图生成能力。候选资产保存在 `/Game/AIAnimationPreview/Candidate24/`，旧资产和默认预览入口保留。

## 同源时间区间的离线质量

ONNX CPU 数值路径测试当前全部 178 条留出片段，其中 170 条具有足够共同区间，8 条过短而跳过。比较每条的源帧 28 至长度减 9，至少 10 帧；不包含模型预热、动作开头和跨动作切换。指标按片段等权平均，不能解释为所有帧池化 RMSE，也不能与其他区间的历史报告计算提升率。

| 指标 | 16 帧基线 | 24 帧首尾条件 | 改善片段 |
| --- | ---: | ---: | ---: |
| 骨骼位置 RMSE（cm） | 5.9136 | 5.2757 | 164/170 |
| 速度误差（cm/帧） | 2.0546 | 1.9333 | 151/170 |
| 位置二阶差分误差（cm/帧²） | 2.1385 | 2.0437 | 125/170 |

这里二阶差分误差相对源动作计算，避免单纯通过静止输出取得低二阶差分。位置均值降低约 10.79%，连续性并非逐片段全部改善。

四条 Traversal 的位置 RMSE：

| 动作 | 基线（cm） | 候选（cm） |
| --- | ---: | ---: |
| Catch_Hurdle_low_run | 13.262 | 11.457 |
| Catch_Hurdle_med_stand | 4.768 | 4.420 |
| Mantle_1_0_run_F_Rfoot | 5.587 | 4.589 |
| Vault_1_0_run_F_Lfoot | 10.280 | 9.170 |

低障碍动作仍有显著偏差，不能声称抽搐或接触问题已经解决。6 条位置均值退化的片段是 Crouch Idle Turn 045 L、Crouch Idle Turn 090 R、Jump F Land Stand Light Rfoot、Run Start B Lfoot、Slide FootOut Out Idle Stand、Walk Spin F LR Lfoot；退化约 0.03–0.27 cm。

同时试验了根据局部旋转和骨盆位置残差调整窗口权重。其整体位置均值仅进一步降低约 0.00065 cm，并使 Mantle/Vault 部分指标退化，因此只保留在离线评估工具，不接入 UE、不作为默认方案。未重新运行此前已否定的外推和骨盆纠正方案。

报告：`output/ai_animation_runtime_candidate24/quality_test.json`、`summary.json`。

## UE 与导出验证

原训练实现、ONNX CPU 校验均通过；UE DirectML 六组夹具最大混合元素绝对误差为 0.000792503，小于 0.01 门限。该值混合位置和旋转元素，不能视为骨骼位置误差。

Windows、RTX 4070 Laptop GPU、1600×900、60 FPS 上限、关闭 VSync，分别运行旧资产和 Candidate24。两轮均有两个渲染角色，一个执行模型重建。六类动作逐项链路验收全部通过，推理失败、回退和 Game Thread 跳过均为零，动作切换与回绕实际发生。它们不等于切换观感、任意 AnimGraph、接触质量或打包验收。

| 指标 | 基线 | Candidate24 |
| --- | ---: | ---: |
| 稳态推理样本数 | 149 | 139 |
| 同步推理平均 / P95（ms） | 2.075 / 2.813 | 2.119 / 2.535 |
| 节点求值平均 / P95（ms，不含源图） | 2.307 / 3.049 | 2.429 / 2.860 |

同步计时包含传输与等待，并非纯 GPU kernel 时间。单轮 P95 下降不证明普遍加速，平均推理和节点耗时略增。长窗口预热导致有效样本区间变化，因此 UE 报告的姿态均值不用于准确率提升百分比。稳态播放延迟仍约 267 ms，从空历史预热更长。

UE 编译成功，实际执行 FixedSampling、PlaybackBuffer、StationaryPlayback 三项自动化测试均成功；Python 三项测试验证快速源动作不被误压制、已播放端点冻结、异常窗口权重降低。没有验证多人并发、长期运行、移动设备或 Shipping。

运行报告位于 `output/ai_animation_runtime_candidate24_baseline/` 和 `output/ai_animation_runtime_candidate24_ue/`，含截图及完整日志。构建和测试日志位于 `.build/ai_animation_candidate24_{build,automation,python_tests}.log`。

## 查看与重跑

从仓库根目录执行，候选方案需已完成导出和导入：

```powershell
# 候选交互预览；关闭窗口结束
./unreal-script/AIAnimation/Run-GaspPreview.ps1 -Variant Candidate24 -Mode Interactive

# 旧方案交互对照
./unreal-script/AIAnimation/Run-GaspPreview.ps1 -Mode Interactive

# 留出集同区间对照；残差加权只在此离线实验中运行
.venv/Scripts/python.exe -m inference.profiling.compare_unreal_streaming --baseline output/ue_animgraph_v2 --candidate output/ue_animgraph_candidate24 --dataset data/prepared/native30_relative_v2_worldcontacts --selection test --output output/ai_animation_runtime_candidate24/quality_test.json
```

重新生成时，导出目录必须是一个尚不存在的新目录；相应替换导入的 ModelFolder：

```powershell
.venv/Scripts/python.exe -m inference.export.export_unreal_animgraph --checkpoint training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt --output output/ue_animgraph_candidate24_new --window_frames 24 --pose-condition endpoints
& D:/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe D:/GameAnimationSample/GameAnimationSample.uproject -run=AIAnimationPrepare -ModelFolder=D:/AILocomotonSystem/GR00T-WholeBodyControl/output/ue_animgraph_candidate24_new -Variant=Candidate24 -ValidateGPU -unattended -nop4 -AllowCommandletRendering
```

导出仍默认 16 帧、无姿态条件；显式选用候选避免静默改变旧实验。Variant 仅允许单个字母、数字、下划线组成的名称，将生成资产隔离在实验目录下。
