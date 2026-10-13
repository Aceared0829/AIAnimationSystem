# 仓库目录与维护说明

本页说明当前职责目录、安装入口和兼容约定。2026-09-12 的迁移映射、验收结果及当时工作区状态见 [历史迁移记录](history/repository-migration-20260912.md)。

## 当前布局

```text
AIAnimationSystem/
├── data/
│   ├── runtime/                  # motionbricks.data：骨架、数据集、格式契约
│   ├── tools/                    # 数据准备、批次处理、审核和入库
│   │   └── review_web/           # 审核网页资源
│   └── prepared/                 # 已有本地 UE 数据，不提交
├── training/
│   ├── pretrain/                 # train_unreal、train_vqvae、train_pose、train_root
│   ├── posttrain/                # 扩展位置；尚无独立后训练算法
│   ├── models/
│   │   ├── vqvae/                # Lightning VQ-VAE 封装
│   │   └── backbone/             # Lightning Pose、Root 封装
│   ├── common/                   # 质量训练、有效帧掩码、采样器
│   │   └── optim/                # 调度器及训练日志工具
│   ├── evaluation/               # 重建评估、容量诊断、评估画廊
│   ├── configs/                  # 现有训练配置
│   └── runs/                     # 本地训练检查点与实验产物，不提交
├── model/
│   └── motionbricks/
│       ├── vqvae/neural_modules/ # 编码器、码本、解码器
│       ├── motion_backbone/      # Pose、Root 网络及共享采样
│       ├── motionlib/core/       # 动作表示、骨架、变换与数学
│       ├── geometry/             # 几何计算
│       ├── helper/               # 兼容名称的共享表示/特征工具
│       └── repository.py         # 与当前工作目录无关的资源定位
├── model-weight/
│   └── base/motionbricks/        # 原 out：权重及绑定的配置、骨架、统计量
├── inference/
│   ├── runtime/
│   │   ├── checkpoint.py         # VQ-VAE 契约加载；评估与导出共用
│   │   ├── backbone/             # 上游生成编排
│   │   └── experiment/           # G1 旧模型加载兼容流程
│   ├── export/                   # FP32 完整/decoder-only 导出
│   ├── profiling/                # CUDA 神经网络性能测量
│   ├── cli/                      # G1 演示入口
│   ├── demo/                     # 演示控制器、界面、MuJoCo 集成
│   └── assets/                   # G1 骨架、网格与上游预览素材
├── unreal-script/
│   ├── AILocomotionSystem/
│   │   └── AILocomotionDataset/  # 完整可复用 UE 插件
│   └── python/                   # UE 宿主内的重定向和验证脚本
├── unreal-sample/                # UMWSamplePreview：UE 5.8 推理/动画工具链实验宿主源码；Content 暂缓交付
├── tests/                       # 回归测试与受控动画夹具
├── docs/                        # 架构、迁移与技术说明
├── launcher/                    # Windows 启动器源码
├── tools/                       # 日常工具；archive/ 保存一次性迁移脚本
├── motionbricks/                # 旧 CLI 委托与本机路径兼容
├── setup.py                     # 唯一有效安装入口
└── pyproject.toml
```

`unreal-sample/UMWSamplePreview/` 保存实验宿主的项目 Gameplay 源码、独立 MotionWeaver 插件与文本配置，供后续接入 UE 内推理及动画工具链；不处理动作数据，也尚未接入模型或推理 AnimGraph。MotionMatchingInCpp 的 CommonGameplay 已并入项目模块，原插件已移除，默认地图与角色使用 `/Game` 下暂未发布的 Content。干净源码检出不能视作可玩示例。`unreal-script/MotionWeaver/` 为 Sample 插件的同步镜像；历史 GASP 预览插件位于 `unreal-script/MotionWeaverCMCPreview/`。边界与历史宿主的区别见 [Unreal 实验宿主说明](../unreal-sample/README.md)。

`data/raw/`、`model-weight/pretrained/`、`finetuned/`、`exported/` 按实际产物需要创建，已配置本地忽略规则。目录名不表示训练、后训练或示例已经完成。

## 安装、兼容与依赖

已有 `.venv` 且依赖齐备时，可重新安装本仓库的可编辑包：

```powershell
uv pip install --python .venv/Scripts/python.exe --no-deps -e .
.venv/Scripts/python.exe -m training.pretrain.train_unreal --help
.venv/Scripts/python.exe -m inference.export.export_unreal_inference --help
.venv/Scripts/python.exe -m data.tools.motion_review_server --help
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

新环境可在根目录安装 `.[training]` 或 `.[training,demo]`；GPU PyTorch 应使用适合目标硬件的构建。旧 `motionbricks/setup.py` 会明确提示安装根目录，避免误装空包。

根目录 `setup.py` 使用明确的 `package_dir` 映射保留旧 Python 名称。训练损失的新权威模块为 `motionbricks.training.unreal_quality`，旧 `motionbricks.data.unreal_quality` 仍为历史 Hydra 配置提供兼容别名。目录迁移没有改写检查点二进制。

新入口支持从任意工作目录执行，前提是已经安装包。wheel 不携带大权重、数据与 UE 工程，使用这些仓库资源时设置 `AIANIMATION_ROOT` 指向完整检出。

UE VQ-VAE 导出与训练评估入口分开；相关依赖隔离由 `tests/test_repository_layout.py` 覆盖。G1 `runtime/experiment/` 仍兼容上游 Lightning 模型封装，尚未重写为独立部署后端。

本机旧 `motionbricks/unreal_data`、`unreal_runs`、`out`、`assets` 为目录连接，指向唯一的新位置。它们保留旧绝对路径读取能力，不复制数据。重建工具为 `tools/install_legacy_paths.ps1`；换机器仍需恢复实际数据，旧机器绝对路径不会自动变成可移植路径。旧 `scripts/*.py` 为委托入口；新代码不依赖旧脚本目录。

## 日常检查与历史审计

从仓库根目录执行 CLI 检查，验证新旧入口能在仓库外工作目录显示帮助：

```powershell
.venv/Scripts/python.exe tools/verify_repository_layout.py --output output/repository-layout-cli.json
```

默认检查不读取迁移当天的本地产物清单，不要求训练数据和权重保持历史大小及修改时间。

需要对照迁移快照时，显式指定原回执目录：

```powershell
.venv/Scripts/python.exe tools/verify_repository_layout.py --output output/repository-migration-audit.json --migration-audit .build/repository-migration-20260912
```

显式审计要求回执中的 `moves.json` 和 `artifact-inventory.json` 均存在；检查缺失文件、大小和修改时间差异，并在有差异时返回非零。它只比较历史元数据，不能据此判定内容损坏或替代 SHA-256 校验。外部数据盘离线、正常训练或恢复 LFS 权重都可能产生差异。

MotionWeaver 的唯一开发源为 `unreal-sample/UMWSamplePreview/Plugins/MotionWeaver/`，`unreal-script/MotionWeaver/` 为同步镜像；同步和 `-Check` 命令见 [插件镜像说明](../unreal-script/README.md#motionweaver-插件镜像)。

## 本地产物保留边界

`.build/` 混有可重建产物与历史证据，不应整目录清理。编译中间产物、已完成下载的分片和临时安装目录可单独评估清理；迁移回执、实验原始证据及 `user-edits/` 等备份需先核对用途和独有内容。文档中的历史本机路径不保证今天仍存在。

工具与文档归档保留旧 Python 名称、CLI 委托和目录连接，不移动本地回执、训练数据、权重或资产备份。
