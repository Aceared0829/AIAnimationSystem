# 旧入口兼容目录

实现已按职责迁至根目录 `data/`、`training/`、`model/`、`inference/` 等目录。安装请在仓库根目录执行 `uv pip install --python .venv/Scripts/python.exe -e . --no-deps`（已有依赖的环境）。

`scripts/*.py` 仅转发旧命令，不保存另一份实现。旧 `out/`、`assets/`、`unreal_data/`、`unreal_runs/` 在本机为目录连接，可用 `tools/install_legacy_paths.ps1` 重建；它们不参与 Git 提交。上游权重和参考资产的唯一归档位置为 `model-weight/base/motionbricks/` 与 `inference/assets/`。

旧检查点记录的绝对数据路径依靠连接继续读取原内容；换机器仍需要恢复数据并配置路径。新代码和新文档使用职责目录。
