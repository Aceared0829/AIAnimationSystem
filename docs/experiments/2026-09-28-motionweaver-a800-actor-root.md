# MotionWeaver Actor Root 条件训练与本地推理

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-28-motionweaver-a800-actor-root`；训练 / 本地推理 |
| 时间 | 2026-09-28，Asia/Hong_Kong；当日完成训练与本地验收 |
| 状态 | 完成实验；正式训练 20000 步，质量未通过玩家 UE 试玩准入 |
| 设备 | 优云智算 A800-SXM4-80GB 一卡；本地推理机器另记 |
| 代码基点 | `e07aad29773bf24dcadd98e36271d3af1894e7fe`，工作树 dirty |

## 问题与实验边界

在保留 MotionBricks UE VQ 码本与 Pose Token 主干的基础上，测试 MotionWeaver 是否能用 4 帧历史姿态和独立 Actor Root 轨迹预测后续姿态。未来真实姿态不作为条件。来源动作的未来 Actor Root 只能作为配对轨迹教师；它不等于玩家 CMC 实时可知的未来轨迹。训练后的本地评估会分别标明配对轨迹和控制器推算轨迹，不能将前者的成绩称为在线玩家结果。

复核发现 `motion_*.npy` 中的 5D root 是 Actor-relative 骨盆/身体特征，独立的 `raw_*.npz/root_track` 才是 Actor 世界轨迹。训练条件、推理接口和评估必须区分两者。由于前者误当 CMC Root 会污染结论，本次在远端训练前新增逐片段的 Actor Root sidecar。

## 数据与传输

- 数据：`E:/AIAnimationSystemData/prepared/native30_relative_v2_worldcontacts`，1722 段，train 1355 / validation 189 / test 178；30 FPS，954D，训练签名 `49c6a9040b8ab20478d5998f0f91d990654b9aa5d9cca6acff34fb7093ba1c88`。
- 匹配 VQ 检查点：`D:/AILocomotonSystem/GR00T-WholeBodyControl/motionbricks/unreal_runs/relative_v2_vqvae_contract_20260909/checkpoints/final.ckpt`，SHA-256 `6ffa1d2db0521f7d331c31741298f328a9714b95335be771f9836d4cc25f79a3`。来自本项目已有 UE VQ 训练，不使用 G1 权重。
- 基础上传包：本机 `.build/motionweaver_a800_20260928.zip`，954622306 字节，SHA-256 `c1a310c1c03607cef838e5afeb9c9eec0614f57dc02a9fb0f8ccefa7c6113000`；远端目标 `/workspace/motionweaver-20260928/`。代码在上传时仍在修订，最终以同步的补丁文件为准。
- Actor Root sidecar：本机 `.build/motionweaver_actor_root_sidecar_20260928.zip`，1827240 字节，SHA-256 `4312b6e50ca3b299871c69f216337c4296fbe0538e4495ff26eb2752f650dfb5`；含 1722 条 `[frames,7]` 米制 Y-up XYZW 轨迹及来源清单。远端上传哈希已核对。
- 训练源码补丁：本机 `.build/motionweaver_actor_root_source_patch_20260928.zip`，18129 字节，SHA-256 `9028421495f25a15cf9db360c2203e24e6a23e1938e7c7ea5c83e13be2f73e27`。覆盖后生效 profile 为 `actor_root_history4_compact_v1`。
- 分区只用 manifest 的 train 行构建训练 DataLoader；validation/test 随包用于之后评估，不参与梯度更新。下文记录了采样、短动作 padding 与固定验证口径的复核。
- train 中 97/1355 条动作源帧数不足 65，prepared 数据以末帧保持补齐；本次沿用现有采样，短静态段可能影响训练分布。

## 实际训练

远端实例 `uhost-1vtl0u7hu42w`，A800-SXM4-80GB；Python 3.12、PyTorch 2.13.0+cu132、PyTorch Lightning 2.6.6。上传包经远端 `sha256sum` 独立核对，使用 `/usr/local/miniconda3/envs/py312/bin/python -m zipfile -e` 解包。远端 editable 安装在 SSH 非交互 shell 下无法解析 `motionbricks`；改用普通 wheel 安装后导入通过。训练入口还要求 `AIANIMATION_ROOT` 指向远端项目目录。这两次失败都发生在正式训练前，未产生有效训练步。

2 步 GPU 烟测通过，冻结 VQ，Pose Backbone 可训练参数 8,278,544；配置 bf16 mixed、batch 2、seed 42，生成了烟测检查点。这只验证梯度/保存链路。

2000 步链路短跑命令在 `.build/launch_a800_train.sh`，run ID `motionweaver_actor_root_compact_v1`，`batch_size=8`、bf16 mixed、seed 42、每 500 步保存。达到 2000 步，远端最终检查点 SHA-256 `656665240807825ecf0304bd18476352776dc27a775ec1ae314e1affadc91a45`；这是短跑，不是正式质量结论。

用户要求与此前训练相同的 20000 步后，未从 2000 步检查点续训，因为旧计划的学习率已按 2000 步衰减。正式训练从相同 VQ 和 seed 42 **重新初始化 Pose Backbone**。远端工作目录为 `/workspace/motionweaver-20260928/project`，执行的核心命令如下；本地完整启动脚本留在 `.build/launch_a800_train_20k.sh`。

```bash
AIANIMATION_ROOT=/workspace/motionweaver-20260928/project \
  /usr/local/miniconda3/envs/py312/bin/python -u -m training.pretrain.train_unreal \
  --model pose --dataset ../dataset --actor_root_sidecar ../actor_root_sidecar \
  --vqvae ../weights/vqvae.ckpt \
  --output ../runs/motionweaver_actor_root_compact_20k_v1 \
  --motionweaver_online --max_steps 20000 --batch_size 8 \
  --checkpoint_every 2000 --accelerator gpu --precision bf16-mixed --seed 42
```

训练日志以 `Trainer.fit stopped: max_steps=20000 reached` 结束。下载后本地 `output/motionweaver_actor_a800_20k_20260928/` 保存 `final.ckpt`、`config.yaml`、`metrics.csv`、`train.stdout.log`；最终检查点本地与远端 SHA-256 一致，为 `5c41d53b2901e6ce38991f729e7394e526fc09a6c9c03874cc30789e9ad13199`。前 100 步平均训练 CE 2.32474 nats，最后 100 步 1.44006 nats；[逐步曲线](assets/2026-09-28-motionweaver-a800-actor-root/training_loss.png)与[聚合值](assets/2026-09-28-motionweaver-a800-actor-root/training_loss_summary.json)保留。A800 实例在本地权重校验后已通过控制台关机，控制台显示“关机”。

## 数据/训练审计

以下为已冻结训练代码、manifest、sidecar 与 20k 检查点的复核。20k 检查点 `global_step=20000`，SHA-256 `5c41d53b2901e6ce38991f729e7394e526fc09a6c9c03874cc30789e9ad13199`；其内嵌配置与下列优化器、调度器及 Actor Root 契约一致。

- `training_indices` 只返回 1355 条 train，validation 189 / test 178 不进入训练 DataLoader；三个分区的 `group`（asset family）两两交集均为 **0**。`MotionWeaverUnrealDataset` 逐条检查 sidecar 的索引、文件名、分区、帧数和 SHA-256。项目脚本 `data/tools/prepare_motionweaver_actor_roots.py` 从 `raw_*.npz/root_track` 重建 1722 条 sidecar；复跑所得 1722 个 `.npy` 和 manifest 与本次上传内容逐字节一致。
- 按 20k 启动参数构建配置：Pose Backbone `n_embd=256`、6 层、8 头；冻结已有 VQ，优化器 `AdamAtan2`，初始学习率 `1e-4`、权重衰减 `0`；`WarmupCosineScheduler` 总 20000 步、预热 1000 步、最终学习率 `2e-6`。有效 profile 是 `actor_root_history4_compact_v1`，每个样本只提供前 4 帧历史姿态条件，未来姿态作为 Token 目标而非输入。源动作未来 Actor Root 仍是训练教师轨迹，不代表实时控制器预测。
- train 中所有 prepared 动作至少 65 帧；网络最长取 16 Token × 4 = 64 帧，采样额外要 1 帧，因此每个 train 动作都满足长度门槛，**不会因长度不足触发 batch skip**。`batch_size=8`、`drop_last=False`、20000 步对应 170 batch/epoch、117 个完整 epoch 加 110 batch，约 **159415 个样本窗口**，每条 train 动作约出现 117 或 118 次。该数为按 DataLoader 逻辑推导，须以最终 global step 和训练日志复核。
- 97/1355 条 train 动作的 `source_frames<65`，已末帧保持补齐。按 clip 均匀抽取、Token 数 6–16 均匀抽取及各可用窗口起点估算，约 **2.81%** 的训练目标帧位于保持区，约 **2.47%** 的采样窗口有超过一半帧处于保持区。这是分布风险估算，不是训练时逐 batch 观测值。
- 独立 Actor Root 的水平逐源帧速度（米/秒，按帧汇总，排除补齐帧）：Walk（48443 帧差）p10/p50/p90 = **1.291/1.650/2.000**；Run（33734）= **1.247/3.750/5.000**；Crouch（40112）= **1.453/1.650/2.250**。评估使用的 `output/cmc_root_capture_20260925_v2.csv` 速度为 Walk **1.4**、Run **4.0**、Crouch **0.8 m/s**：Walk 靠近训练低端，Run 在主分布内，**Crouch 0.8 低于训练 p10，属于明显低速分布偏移**。Crouch 若出现步幅/落脚不匹配，应把这项偏移列入原因分析；目前模型也没有显式 Crouch 状态输入。

固定 validation Token CE 使用相同 48 条片段（Walk/Run/Crouch 各 16 条）、相同 2608 个监督 Token、seed 1701，且两次记录的 manifest、sidecar 哈希与索引完全相同。结果保存在 `assets/2026-09-28-motionweaver-a800-actor-root/val_token_ce_2k.json` 与 `assets/2026-09-28-motionweaver-a800-actor-root/val_token_ce_20k.json`。

| Validation 类别 | 目标 Token | 2k CE (nats) | 20k CE (nats) | 相对变化 |
| --- | ---: | ---: | ---: | ---: |
| 总体 | 2608 | 1.861950 | 1.453611 | -21.93% |
| Walk | 922 | 1.740686 | 1.188714 | -31.71% |
| Run | 953 | 1.980851 | 1.684734 | -14.95% |
| Crouch | 733 | 1.859894 | 1.486319 | -20.09% |

这是**源 Actor Root 教师轨迹**下的 masked Pose Token 交叉熵，仅证明此固定验证子集的 Token 预测改善；不代表控制器 Root 条件下的世界姿态、接触或 UE 实时效果。2k 短跑与 20k 正式训练分别使用 2000/20000 步的调度器配置，也不是单独控制训练步数的消融。

## 本地无未来姿态推理验收

本地 RTX 4070 Laptop GPU 加载 A800 的 20000 步权重。每段使用前 4 帧来源姿态，生成后 24 帧；**不输入未来真实姿态**。可复现命令、骨架可视化口径和原始输出目录见[本地验收说明](../../inference/visualization/README.md)，合并指标见[20k 验收 JSON](assets/2026-09-28-motionweaver-a800-actor-root/motionweaver_20k_acceptance_summary_20260928.json)。旧直接回归模型使用 24 帧姿态历史，而 MotionWeaver 使用 4 帧；下表是现有产品路线参照，不能解释成只有架构变化的严格消融。

第一组测试给两个模型**同一条来源导出的未来 Actor Root**，对比同一测试片段的世界骨架。未来 Actor Root 是离线配对教师轨迹，不是玩家实际可提前取得的轨迹。RMSE 为未来 24 帧、79 骨世界关节误差。

| 测试片段 | 旧模型 RMSE | MotionWeaver 20k RMSE | 来源接触脚速 | 旧模型接触脚速 | 20k 接触脚速 | 接触帧对数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Walk Loop 1403 | 6.72 cm | **6.03 cm** | 0.031 m/s | 0.681 m/s | **0.780 m/s** | 5 |
| Run Loop 820 | **7.36 cm** | 12.00 cm | 无法测 | 无法测 | 无法测 | 0 |
| Crouch Loop 145 | **5.87 cm** | 8.25 cm | 0.073 m/s | 1.141 m/s | 0.875 m/s | 2 |

三栏 Walk/Run/Crouch 骨架视频保留在本地实验归档，不随公开仓库发布；[旧模型逐条报告](assets/2026-09-28-motionweaver-a800-actor-root/old_teacher_report.json)、[MotionWeaver 逐条报告](assets/2026-09-28-motionweaver-a800-actor-root/motionweaver_teacher_report.json)及[同轨校验](assets/2026-09-28-motionweaver-a800-actor-root/comparison.json)保存在仓库。骨架视频可看步态和轨迹，但本轮尚未用 UE 角色蒙皮播放。接触脚速只在来源接触标签连续两帧成立时计算；Run Loop 没有这样的帧对，Crouch Loop 只有 2 对，因此另测以下更有接触的停止片段。

| 接触较多的片段 | 来源脚速 | 旧模型脚速 | MotionWeaver 20k 脚速 | 接触帧对数 |
| --- | ---: | ---: | ---: | ---: |
| Walk Stop 1653 | 0.035 m/s | 0.321 m/s | **0.276 m/s** | 11 |
| Run Stop 898 | 0.027 m/s | 0.847 m/s | **0.166 m/s** | 20 |
| Crouch Stop 411 | 0.0067 m/s | **0.127 m/s** | 0.186 m/s | 24 |

Stop 测试说明有局部落脚改善，但 Walk Loop 仍明显滑，Crouch Stop 反而变差；不能称作脚滑已经解决。[MotionWeaver](assets/2026-09-28-motionweaver-a800-actor-root/motionweaver_contact_stops_report.json)与[旧模型](assets/2026-09-28-motionweaver-a800-actor-root/old_contact_stops_report.json)的原始逐条报告已保存；该比较仅对相同来源 Actor Root 路径有效。

第二组测试改用**另行录制的 UE CMC Actor Root**：[CMC 轨迹 CSV](assets/2026-09-28-motionweaver-a800-actor-root/cmc_root_capture_20260925_v2.csv) 的 44–71 帧，前 4 帧历史来自来源片段，后 24 帧用与第 4 历史帧刚性对齐的 CMC 轨迹。Walk/Run/Crouch CMC 平均速度分别约 1.4/4.0/0.8 m/s，并有约 90° Actor 转向。来源姿态在 CMC 轨迹上的画面是反事实视觉参照，不是这条新轨迹的真实答案；不得用它报告有效的世界姿态 RMSE 或脚滑。Crouch 片段 430 的 CMC 捕获带有蹲伏状态，但**没有输入 MotionWeaver**。本地归档的站→蹲中帧及视频显示来源姿态下蹲而模型仍直立。改变 Actor 路径后，模型生成的 Actor 局部关节姿态 RMS 只变化 **0.50 cm**，未来 Token 仅 **2.1%** 改变；世界朝向的大部分改变来自外部 Actor 旋转，不能当成模型学会转弯或蹲伏。[CMC 逐条报告](assets/2026-09-28-motionweaver-a800-actor-root/motionweaver_cmc_report.json)已保存，另两段 CMC 视频留在本地 `output/motionweaver_actor_20k_cmc_20260928/`。

解码器诊断在保持 Pose Tokens 完全相同的情况下，偷偷给 VQ 解码器来源未来 pose-feature Root：Walk/Run/Crouch 世界关节 RMSE 分别从 6.03/12.00/8.25 降到 4.86/11.06/6.48 cm。[逐条结果](assets/2026-09-28-motionweaver-a800-actor-root/motionweaver_decoder_oracle_report.json)已保存。这是**未来真值泄漏的离线上界诊断**，证明缺少合理的解码器 pose-root 条件是部分误差来源，不能作为可部署效果，也不能单凭这组数解释全部脚滑。

本地 Python eager 模型 forward，同步计时 9 次，P50 18.24 ms、P95 21.04 ms；该值不含数据准备、UE NNE、蒙皮、渲染、线程调度或真实重规划闭环，不能宣称 UE 实时预算已经通过。三条同轨比较视频和三条 CMC 视频均已检查为可解码的 28 帧片段。

## 结论、限制与下一步

**这轮按用户要求完成了从零训练的 20000 步，但不通过“玩家可操控时姿态与位移一致、可靠蹲伏、无明显脚滑”的质量门槛。** 固定 validation Token CE 改善 21.93%，Walk Loop 姿态略好；Run/Crouch 姿态、Walk Loop 接触脚速以及 CMC 站→蹲仍有明确失败样例。模型不应替换当前 UE 试玩 ONNX 或宣称已有 UE 蒙皮实跑结果。

当前 manifest 只有片段级 `action/category/phase` 等标签；`raw_*.npz` 只有 `positions/rotations/timestamps/root_track`，**没有逐帧 `desired_stance`、玩家蹲键或 CMC 状态轨道**。明确命名的 Stand↔Crouch 动画仅 4 条、每条 76 源帧：train 3（Stand→Crouch 1、Crouch→Stand 2）、test 1（Stand→Crouch）、validation 0。可从资产名区分稳态姿势候选，但不能用这份数据证明“按键触发蹲下”的因果响应；骨盆高度是实际姿态的几何结果，不能伪装成玩家输入。下一版若训练显式目标姿势条件，需要同步录制 UE 玩家输入、CMC/Mover 状态和 Actor Root，或给过渡资源建立可信的人工逐帧时序标注。

下一轮先补真实可在线取得的轨迹/状态条件，并建立 CMC 速度与蹲伏状态覆盖；再针对 Actor Root 与 VQ 解码器 pose-root 条件、落脚接触和速度相位做受控实验。每一项用相同冻结片段分别验 Token CE、世界姿态、接触脚速和 UE 蒙皮/玩家闭环；当前 20k 权重保留为可复现基线。

## 完成核对

- [x] Actor Root sidecar、窗口裁剪和世界坐标单步检查；世界平移及 90° 旋转变换检查通过。
- [x] A800 安装、正式命令、种子、批量、20000 步、损失曲线、检查点 SHA 和本地下载复核。
- [x] 本地来源 Actor Root 与另录 CMC Actor Root 推理、姿态和接触指标、可解码骨架视频。
- [x] 旧模型同来源 Actor Root 对照；来源未来轨迹与 CMC 控制器轨迹分开报告。
- [ ] MotionWeaver 20k 权重的 UE NNE/AnimGraph 接入、角色蒙皮和可操作闭环。本实验未执行。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-28 | 建立进行中记录，记录上传包与 Actor Root 契约问题 | 本地代码/数据检查与远端 A800 连接核验 |
| 2026-09-28 | 从零完成 20000 步，补固定 validation、来源与 CMC 推理及失败样例，关闭实验 | 检查点/日志、逐条报告与本地视频；A800 控制台关机状态 |
