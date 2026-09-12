# 模型产物

`base/motionbricks/`：已有上游权重及对应配置、骨架和统计量，保留原版本内结构。权重使用 Git LFS，并继续适用 NVIDIA Open Model License。

`pretrained/`、`finetuned/`、`exported/`：可按需创建本地预训练产物、后训练产物、推理导出包；默认不提交。训练中间检查点归 `training/runs/`。

导出包由导出器记录骨架/统计量签名、权重和码本哈希。目录名不证明模型已训练或通过质量验收。

需要上游权重时，从根目录执行 `git lfs pull --include="model-weight/base/**" --exclude=""`。迁移已改变未提交工作树路径；迁移提交前远端仍可能使用旧路径 `motionbricks/out/**`，不要把本地重组当成远端已发布。
