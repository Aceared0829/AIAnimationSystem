# 推理与部署验证

`runtime/checkpoint.py` 提供受数据契约保护的 VQ-VAE 加载，供训练评估和推理导出共用；不导入训练 CLI 或绘图库。

`runtime/backbone/` 保留上游生成编排；`runtime/experiment/` 是 G1 参考演示兼容加载路径，仍需 Lightning 模型封装。它与轻量 UE VQ-VAE 导出路径的依赖要求不同。

`export/` 导出 FP32 权重、骨架、统计量和契约；`profiling/` 测量神经网络推理与实验播放质量；`cli/`、`demo/`、`assets/` 提供 G1 MuJoCo 参考演示。

```powershell
python -m inference.export.export_unreal_inference --help
python -m inference.export.export_unreal_animgraph --help
python -m inference.profiling.profile_unreal_inference --help
python -m inference.profiling.evaluate_unreal_streaming --help
python -m inference.cli.interactive_demo_g1 --help
```

`export_unreal_inference` 保留 PyTorch 导出包。`export_unreal_animgraph` 为 `AIAnimation` Inference Lab 导出固定窗口 ONNX、骨架契约和数值验证夹具；它接收 Root 相对的已知源姿态，不是玩家意图驱动的动作生成。`evaluate_unreal_streaming` 在 CPU 数值路径上对齐相同源时间区间，评估末帧与延迟融合播放的姿态和连续性；它不测 UE GPU 性能。完整 UE 导入、DirectML 校验和实验边界见 [AIAnimation 实验说明](../unreal-script/AIAnimation/README.md)。G1 演示仍需安装 `.[demo]` 并准备对应权重。

2026-09-12 已在当前 `.venv` 补齐 MuJoCo 与 G1 权重，并通过实际生成、渲染和中文窗口验收，见 [G1 演示验收](../docs/g1-demo-acceptance.md)。
