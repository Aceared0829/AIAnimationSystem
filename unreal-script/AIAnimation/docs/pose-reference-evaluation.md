# Traversal 多参考姿态消融（2026-09-23）

本轮开始前已将 Candidate24 基线以 `7c0aeb9` 提交并推送到 `origin/codex/ai-animation-inference-lab`。以下为提交之后的独立实验，未替换 UE 候选资产或默认行为。

## 方法

- 相同 relative_v2 权重，24 帧历史、步长 4、播放延迟 8，保持现有融合与静止保护。
- PyTorch CUDA FP32，关闭 TF32，仅评估数值质量，不测 UE 或实际 GPU 性能。
- 覆盖当前留出集全部 4 条 Traversal，另用 Walk、Run、Crouch、Jump、Idle 各一条作对照，共 9 条。
- 每条比较源帧 28 至长度减 9 的共同稳态区间，不包括动作开头、切换或全部未见动作。
- 所有模式保留窗口首尾。均匀模式等距取 3/5 帧；关键模式贪心选取相对已有参考的线性位置插值误差最大帧，手脚权重为 4，其余骨骼权重为 1，参考之间至少间隔 3 帧。
- 每个窗口仅使用已经收到的源姿态。这里的“关键”是几何曲线代表性，不是人工标注的接触、腾空或落地语义。
- 首尾两帧结果与已验证的 Candidate24 ONNX 报告在相同片段和区间上的平均位置误差最大差约 0.0000023 cm，基线一致。

## 结果

单位为平均骨骼位置 RMSE（cm）：

| 动作 | 首尾2帧 | 均匀3帧 | 关键3帧 | 均匀5帧 | 关键5帧 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Catch_Hurdle_low_run | 11.457 | 11.502 | 11.351 | 10.656 | 10.622 |
| Catch_Hurdle_med_stand | 4.420 | 4.537 | 4.400 | 4.582 | 4.463 |
| Mantle_1_0_run_F_Rfoot | 4.589 | 4.642 | 4.452 | 4.580 | 4.578 |
| Vault_1_0_run_F_Lfoot | 9.170 | 9.338 | 9.158 | 8.693 | 8.025 |
| 四条等权平均 | 7.409 | 7.505 | 7.340 | 7.128 | 6.922 |

关键3帧的四条位置均值均有改善，但整体收益约 0.93%。关键5帧整体改善约 6.58%，Vault 改善约 12.5%，中障碍动作则轻微退化。不能据此声称所有 Traversal 都需要 5 帧。

| 四条等权平均指标 | 首尾2帧 | 关键3帧 | 关键5帧 |
| --- | ---: | ---: | ---: |
| 手脚位置 RMSE（cm） | 9.015 | 8.973 | 8.321 |
| 速度误差（cm/帧） | 3.253 | 3.236 | 3.192 |
| 二阶差分误差（cm/帧²） | 3.410 | 3.412 | 3.426 |

更多参考有助于部分姿态准确性，但没有证明能解决抽搐：关键5帧的二阶差分误差反而略增。可能需要持续追踪参考帧身份，减少窗口移动造成的条件切换，但本轮未验证该假设。

均匀3帧的四条位置均值全部退化，说明增加条件数量本身不足以保证改善。下一步应关注按动作阶段选择参考、参考跨窗口保持，以及接缝连续性，不能直接将所有动作切为5帧条件。

## 复现与边界

```powershell
.venv/Scripts/python.exe -m inference.profiling.evaluate_pose_references --checkpoint training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt --output output/ai_animation_runtime_pose_references/showcase.json
.venv/Scripts/python.exe -m unittest inference.profiling.test_pose_references -v
```

JSON 保存逐片段均值、P95、最大值、每窗口所选参考索引，以及位置、手脚、旋转、速度、二阶差分误差。`--selection test` 可扩展为全部留出集，本轮没有执行该扩展。

没有执行末端外推、骨盆直接纠正、重训练或 UE 新模型部署。当前交互预览仍为已验证的 Candidate24 首尾两帧方案。本报告记录软参考消融；后续手选和硬约束见[实验室](../../../inference/profiling/pose-reference-lab.md)。
