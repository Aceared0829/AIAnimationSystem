# 仓库目录与迁移验收

2026-09-12。本次重组将源码和产物按职责归档，保留 MotionBricks 导入名称、上游归属、UE 插件标识及现有数据契约。

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
│   └── runs/                     # 原 unreal_runs，保留所有实验产物
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
├── unreal-sample/                # 当前仅交付约定，无现成 .uproject
├── tests/                       # 回归测试与受控动画夹具
├── docs/                        # 架构、迁移与技术说明
├── launcher/                    # Windows 启动器源码
├── tools/                       # 迁移、路径兼容和目录验证工具
├── motionbricks/                # 旧 CLI 委托与本机路径兼容
├── setup.py                     # 唯一有效安装入口
└── pyproject.toml
```

`data/raw/`、`model-weight/pretrained/`、`finetuned/`、`exported/` 按实际产物需要创建，已配置本地忽略规则。目录名不表示训练、后训练或示例已经完成。

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

## 安装、兼容与依赖

已有 `.venv` 依赖不变，只重新安装本仓库的可编辑包：

```powershell
uv pip install --python .venv/Scripts/python.exe --no-deps -e .
.venv/Scripts/python.exe -m training.pretrain.train_unreal --help
.venv/Scripts/python.exe -m inference.export.export_unreal_inference --help
.venv/Scripts/python.exe -m data.tools.motion_review_server --help
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

新环境可在根目录安装 `.[training]` 或 `.[training,demo]`；GPU PyTorch 应使用适合目标硬件的构建。旧 `motionbricks/setup.py` 会明确提示安装根目录，避免误装空包。

根目录 `setup.py` 使用明确的 `package_dir` 映射保留旧 Python 名称。训练损失的新权威模块为 `motionbricks.training.unreal_quality`，旧 `motionbricks.data.unreal_quality` 仍为历史 Hydra 配置提供兼容别名。目录迁移没有改写检查点二进制。

新入口支持从任意工作目录执行，前提是已经安装包。普通 wheel 安装的代码和审核网页资源已验证；wheel 不携带大权重、数据与 UE 工程，使用这些仓库资源时设置 `AIANIMATION_ROOT` 指向完整检出。

UE VQ-VAE 导出不再导入训练评估脚本，纯网络/导出导入检查主动阻止 Lightning、训练 CLI、Matplotlib 和 MuJoCo，验证通过。G1 `runtime/experiment/` 仍兼容上游 Lightning 模型封装，尚未重写为独立部署后端。

本机旧 `motionbricks/unreal_data`、`unreal_runs`、`out`、`assets` 为目录连接，指向唯一的新位置。它们保留旧绝对路径读取能力，不复制数据。重建工具为 `tools/install_legacy_paths.ps1`；换机器仍需恢复实际数据，旧机器绝对路径不会自动变成可移植路径。旧 `scripts/*.py` 为委托入口；新代码不依赖旧脚本目录。

## 实际验收结果

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

## 工作区与回执

原有未提交修改已随文件迁移保留；迁移前副本位于 `.build/repository-migration-20260912/user-edits/`。旧 EXE 副本为该目录的 `MotionBricks-before.exe`。

本次未提交或推送。为使本机兼容目录连接不造成资产重复跟踪，114 个资产/权重重命名已成对暂存；其余源码变更仍在工作区，可统一审阅后提交。

本机详细回执：`.build/repository-migration-20260912/moves.json`、`artifact-inventory.json`、`layout-verification.json`、`tests-final.log`。UE 插件打包结果位于 `.build/ue-layout/`。这些是本机验证产物，不提交到源码仓库。
