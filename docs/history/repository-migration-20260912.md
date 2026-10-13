# 2026-09-12 仓库目录迁移记录

本文保留目录迁移验收阶段的历史快照。测试数量、依赖状态、LFS 指针及 Git 暂存状态均属于当时记录，不表示当前工作区状态，也不构成今天重新运行的验收结果。

当前目录和使用入口见 [仓库目录说明](../repository-layout.md)。后续 [G1 演示部署验收](../g1-demo-acceptance.md) 已记录演示依赖安装、四份权重恢复和生成、渲染及中文窗口验证；下文迁移阶段的 G1 限制不能作为当前状态说明。

## 主要迁移映射


| 原位置 | 当前位置 |
| --- | --- |
| motionbricks/motionbricks/data | data/runtime；质量训练移至 training/common |
| motionbricks/motionbricks/vqvae/neural_modules | model/motionbricks/vqvae/neural_modules |
| motionbricks/motionbricks/*/models | training/models |
| motionbricks/scripts/train_* | training/pretrain |
| motionbricks/scripts/evaluate_*、画廊与容量诊断 | training/evaluation |
| motionbricks/scripts/数据工具 | data/tools |
| motionbricks/scripts/export_unreal_inference.py | inference/export/export_unreal_inference.py |
| motionbricks/scripts/profile_unreal_inference.py | inference/profiling/profile_unreal_inference.py |
| motionbricks/scripts/unreal | unreal-script/python |
| Unreal/AILocomotionSystem | unreal-script/AILocomotionSystem |
| motionbricks/out、assets | model-weight/base/motionbricks、inference/assets |
| motionbricks/unreal_data、unreal_runs | data/prepared、training/runs |

## 迁移阶段实际验收结果


| 检查 | 结果与范围 |
| --- | --- |
| 迁移前基线 | 47 项 unittest 通过 |
| 迁移后完整测试 | 51 项通过，62.904 秒 |
| 数据与训练回归 | 转换、Root 分离、有效帧、留出划分、审核、入库；VQ-VAE/Pose/Root CPU 小网络训练和续训；不匹配码本拒绝 |
| CPU 导出闭环 | Pose-only 夹具训练，完整包及 decoder-only 导出、加载；CPU 输出 `rtol=0, atol=0` 一致 |
| GPU 冒烟 | RTX 4070 Laptop，PyTorch 2.14.0+cu130；一步训练，完整包及 decoder-only CUDA 前向计时运行成功 |
| 旧检查点 | 原 relative_v2_smoke_vqvae/final.ckpt 经旧数据连接成功加载，220,489 参数 |
| 新旧 CLI | 62 个入口从仓库外工作目录执行 `--help` 通过；motion_batch_gate 是纯辅助模块，不计为 CLI |
| Python 包 | 根目录 editable 安装成功；wheel 构建、隔离路径导入及审核网页资源校验通过 |
| UE 插件 | D:/UE_5.8 BuildPlugin；迁移后插件编译、链接、打包成功 |
| Windows 启动器 | .NET 10 Release 构建零警告零错误，重新发布并更新根目录 EXE |
| 数据与产物保留 | 24,437 个文件与迁移前大小/修改时间清单一致；这是元数据检查，不冒充全数据逐字节哈希验证 |
| 权重与参考资产迁移 | 114 个 Git 纯重命名，0 行内容差异；本地兼容连接已排除跟踪 |

首次 UE 打包输出路径过长，触发 Windows 260 字符限制；改用较短的 `.build/ue-layout` 后编译成功，无需修改插件代码。

G1 图形演示未完整运行：本环境缺少 MuJoCo，四份上游检查点仍为 LFS 指针。此次验证了演示参数入口和启动器构建，未把这些结果当成 G1 生成/界面验收。目录重组不包含新增 UE 运行时推理或新示例地图，也未重新运行生产批次或长期训练。

## 迁移阶段工作区与回执

原有未提交修改已随文件迁移保留；迁移前副本位于 `.build/repository-migration-20260912/user-edits/`。旧 EXE 副本为该目录的 `MotionBricks-before.exe`。

本次未提交或推送。为使本机兼容目录连接不造成资产重复跟踪，114 个资产/权重重命名已成对暂存；其余源码变更仍在工作区，可统一审阅后提交。

本机详细回执：`.build/repository-migration-20260912/moves.json`、`artifact-inventory.json`、`layout-verification.json`、`tests-final.log`。UE 插件打包结果位于 `.build/ue-layout/`。这些是本机验证产物，不提交到源码仓库。

## 归档脚本

三个一次性脚本见 [迁移工具归档](../../tools/archive/repository-migration-20260912/README.md)。本地 `.build/repository-migration-20260912/` 回执、旧用户修改备份和 UE 资产备份仍在原位置，未随文档归档移动或删除。
