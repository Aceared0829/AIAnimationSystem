# 推理与部署验证

`runtime/checkpoint.py` 提供受数据契约保护的 VQ-VAE 加载，供训练评估和推理导出共用；不导入训练 CLI 或绘图库。

`runtime/backbone/` 保留上游生成编排；`runtime/experiment/` 是 G1 参考演示兼容加载路径，仍需 Lightning 模型封装。它与轻量 UE VQ-VAE 导出路径的依赖要求不同。

`export/` 导出 FP32 权重、骨架、统计量和契约；`profiling/` 测量神经网络推理；`cli/`、`demo/`、`assets/` 提供 G1 MuJoCo 参考演示。

```powershell
python -m inference.export.export_unreal_inference --help
python -m inference.profiling.profile_unreal_inference --help
python -m inference.cli.interactive_demo_g1 --help
```

现有导出包是 PyTorch 格式；本次目录重组不增加 UE AnimGraph 推理实现。G1 演示需安装 `.[demo]` 并准备对应权重。

2026-09-12 已在当前 `.venv` 补齐 MuJoCo 与 G1 权重，并通过实际生成、渲染和中文窗口验收，见 [G1 演示验收](../docs/g1-demo-acceptance.md)。
