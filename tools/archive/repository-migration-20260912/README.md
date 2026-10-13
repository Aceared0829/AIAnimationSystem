# 2026-09-12 目录迁移工具归档

这些脚本用于已完成的仓库职责目录迁移，保留供源码追溯。它们不是日常维护命令，不应在当前目录布局上重新运行；归档没有执行迁移或改写本地回执。

| 原执行顺序 | 脚本 | 用途与前提 |
| --- | --- | --- |
| 1 | `reorganize_repository.py` | 面向迁移前目录移动源码和产物、改写导入、生成兼容入口与回执；目标目录已存在或回执存在时会拒绝继续 |
| 2 | `update_layout_references.py` | 读取回执中的 `moves.json`、`scripts.json`，按迁移映射改写跟踪的 Markdown 文档 |
| 3 | `finish_layout_references.py` | 对迁移阶段文档进行剩余路径和安装命令替换 |

三个脚本的仓库根目录定位已适配归档位置。后两个脚本执行时会直接写文件，其中安装命令替换不保证重复执行安全；不要导入它们进行检查。只做语法验证即可。

回执位置仍为 `.build/repository-migration-20260912/`，不随脚本移动。历史范围与限制见 [迁移记录](../../../docs/history/repository-migration-20260912.md)。

日常 CLI 检查继续使用 `tools/verify_repository_layout.py`；旧路径重建继续使用 `tools/install_legacy_paths.ps1`。显式历史审计用法见 [仓库维护说明](../../../docs/repository-layout.md#日常检查与历史审计)。
