# G1 演示部署验收 · 2026-09-12

当前 Python 3.12 `.venv` 原先按训练依赖配置，未安装 MuJoCo；目录迁移时只重装了 `motionbricks`，没有卸载 MuJoCo 的记录。本次安装演示依赖，并将演示所需四份 LFS 权重与 G1 网格恢复为实际文件。

环境：MuJoCo 3.13.0、PyTorch 2.14.0+cu130、RTX 4070 Laptop GPU、Tk 8.6。PyTorch 保持原版本。Transformers 固定兼容的 4.x 范围；避免 5.x CLI 依赖引入 Rich 后改变原训练环境的进度显示行为。最终依赖检查通过。

本轮按用户要求只验收 G1 演示：

- 实际加载 VQ-VAE、Pose、Root 预训练网络及 G1 动作缓存。
- 180 帧生成循环、11 次模型预测、60 张 MuJoCo 渲染帧。
- 180 × 36 的 qpos 和刚体坐标均为有限值；根平面净位移约 2.885 米。
- 中文窗口实际显示正常，可见 G1 角色、运行控制、相机控制和键盘说明。
- 四份检查点大小与 SHA-256 记录在本机 `.build/g1-demo-acceptance/report.json`；Pose 权重下载后与 Git LFS SHA-256 完全一致。

启动：双击仓库根目录 `MotionBricks.exe`。也可从根目录运行：

```powershell
.venv/Scripts/python.exe -m inference.cli.interactive_demo_g1 --chinese_ui 1
```

自动演示：增加 `--controller random`。默认键盘模式使用 WASD 移动，其他动作键见中文面板。

本次验证的是 G1 预训练动作生成与 MuJoCo 运动学显示，不代表 UE 动画运行时或机器人动力学控制验收。演示使用 `G1-clip.ckpt` 即可，不需要重新下载完整 BONES-SEED 数据。

本机记录：`.build/g1-demo-acceptance/report.json`、`g1-preview.png`、`g1-motion.gif` 及 `.build/g1-demo-gui.*.log`。
