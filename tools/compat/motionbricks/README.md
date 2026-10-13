# 旧入口兼容源码

实现已按职责迁至根目录 `data/`、`training/`、`model/`、`inference/` 等目录。安装请在仓库根目录执行 `uv pip install --python .venv/Scripts/python.exe -e . --no-deps`（已有依赖的环境）。

`scripts/*.py` 仅转发旧命令，不保存另一份实现。旧 `out/`、`assets/`、`unreal_data/`、`unreal_runs/` 在本机为目录连接，可用 `tools/install_legacy_paths.ps1` 重建；它们不参与 Git 提交。上游权重和参考资产的唯一归档位置为 `model-weight/base/motionbricks/` 与 `inference/assets/`。

本目录位于 `tools/compat/motionbricks/`，根目录旧 `motionbricks/` 仅为本机兼容连接。旧检查点记录的绝对数据路径依靠连接继续读取原内容；换机器仍需要恢复数据并配置路径。新代码和新文档使用职责目录。Python 发行包与模型导入名已改为 `motionweaver`，本目录的 `__init__.py` 仅注册 `motionweaver.legacy` 中的历史导入别名，不包含模型实现。安装元数据统一生成在 `.build/python/`，实验输出位于 `.build/experiments/`。
