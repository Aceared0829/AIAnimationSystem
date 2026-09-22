# 起手、鲜明中间姿态与结束姿态复测（2026-09-23）

本轮将“位置曲线插值误差大”与“姿态形状鲜明”区分开。新选择器移除骨盆整体平移，以手脚加权的骨盆相对骨骼位置距离，选择距离已有参考最远的姿态；首尾固定，中间选一或两帧，最小间隔3帧。它是几何代表性算法，不是接触/腾空语义标注。动画资产第一帧和最后一帧也不一定等同于人工定义的起手与落地完成。

## 24帧在线历史窗口对照

保持权重、24帧历史、4帧步长、8帧延迟和现有融合，覆盖4条留出Traversal及5条其他动作。所有模式仅使用已收到的历史，逐动作源帧28至长度减9对齐。PyTorch CUDA FP32，关闭TF32，不测UE性能。

位置RMSE均值（cm）：

| 动作 | 首尾2帧 | 首尾+1个形状参考 | 首尾+2个形状参考 |
| --- | ---: | ---: | ---: |
| 低障碍 | 11.457 | 11.067 | 10.863 |
| 中障碍 | 4.420 | 4.390 | 4.430 |
| Mantle | 4.589 | 4.496 | 4.525 |
| Vault | 9.170 | 9.154 | 8.990 |
| 四条等权平均 | 7.409 | 7.277 | 7.202 |

一个中间参考四条均有小幅改善，平均改善约1.79%；两个中间参考均值改善约2.80%，但中障碍退化。速度误差均值为3.253→3.231/3.240 cm/帧；二阶差分误差为3.410→3.433/3.430 cm/帧²。不能声称抽搐改善。

该组仍是窗口首尾，不是整段动作起手与结束。四条完整动作有68–121帧，24帧窗口无法同时包含完整动作的首尾。

## 完整已知动作对照

为直接测试“整段动作起手—鲜明中间—结束”，另对每条动作进行一次完整上下文重建。网络长度补齐至4的倍数；使用全部已知动作，包含未来信息，无滑动播放融合。所有该组方案使用相同上下文和全部真实源帧。输入长度68–124超过训练基础窗口上限64，因此只是离线诊断，不能据此部署或与上表计算提升率。

| 动作 | 整段首尾2帧 | 整段首尾+1个中间姿态 | 整段首尾+2个中间姿态 |
| --- | ---: | ---: | ---: |
| 低障碍 | 9.244 | 8.882 | 8.806 |
| 中障碍 | 4.813 | 4.662 | 4.716 |
| Mantle | 7.574 | 7.608 | 7.178 |
| Vault | 8.094 | 8.060 | 8.162 |

三个参考帧索引分别为：[0,56,102]、[0,52,120]、[0,13,67]、[0,33,94]。参考源骨架图保存在 `output/ai_animation_runtime_pose_references/action_reference_poses.png`，用于核对自动选择是否符合期望动作含义。不能把这些选择直接称作人工认可的语义关键姿态。

两组结果都支持进一步研究姿态选择，但不支持“补一两个姿态必然解决偏差或抽搐”。现有解码器是软条件，选中姿态不等于输出必须经过它。下一步应先确认动作阶段和关键姿态，再研究跨窗口参考身份保持、关键时刻输出残差与约束强度，避免继续单纯增加帧数。

## 复测

```powershell
.venv/Scripts/python.exe -m inference.profiling.evaluate_pose_references --checkpoint training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt --reference-set shape --output output/ai_animation_runtime_pose_references/window_shape.json
.venv/Scripts/python.exe -m inference.profiling.evaluate_action_references --checkpoint training/runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt --output output/ai_animation_runtime_pose_references/action_shape.json
.venv/Scripts/python.exe -m unittest inference.profiling.test_pose_references -v
```

两组均已实际执行完成。四项选择器测试验证数量、间隔、确定性、非中心姿态极值及整体平移不改变形状选择。本轮未更改权重、正式导出器或UE资产，未重新训练；交互预览仍是Candidate24首尾两帧版本。
