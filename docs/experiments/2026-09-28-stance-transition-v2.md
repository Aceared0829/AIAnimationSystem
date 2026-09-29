# 站蹲早期过渡窗口与旧模型无参考诊断

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-09-28-stance-transition-v2`；数据索引 / 本地推理评估 |
| 执行时间 | 2026-09-28，Asia/Hong_Kong；B0 约 16:32，B1 云端训练及本地复测约 17:00 |
| 状态 | v2 索引、B0、B1 云端试验训练和本地冻结测试片段推理完成；不是 UE 玩家闭环 |
| 来源 | AIAnimationSystem 的本地封版 UE 动作、P0 人工方向复核和旧条件模型 |
| 前序记录 | [P0 站蹲数据审计](2026-09-25-p0-stance-data-audit.md) |

## 问题与方案

四条明确 `Stand↔Crouch` 动作的主要过渡位于第 3–17 帧。v1 以 24 帧真实历史作为输入，最早从第 24 帧预测，因此未来窗口里没有主要过渡。v2 仅在片段开头用已观察的第 0 帧补足历史，最早未来从第 1 帧开始；未来始终是真实帧。数据条件新增目标站蹲状态代理标签，来源是旧动画的已复核方向，不当作真实玩家请求、CMC 批准状态或 `can_uncrouch`。

方向来自 P0 逐帧骨架复核；本轮暂用骨盆高度 10%–90% 的相位帧作过渡区间，状态仍标为 `provisional`。v1 的源 NPZ、划分、统计量、检查点均未改写。B0 使用旧权重、无姿态参考、原动作未来 Root，在新窗口直接推理；对照是保持最后已观察姿态。

## 代码、环境与数据

- 基础提交：`e07aad2`（`origin/main`）；本轮实验运行于 `codex/motionweaver-stance-root` 未提交工作区。相关新文件：`data/runtime/stance_motion.py`、`data/tools/build_stance_motion_index.py`、`data/annotations/stance_transition_p0_provisional.json`、`training/evaluation/evaluate_stance_transition.py`、`training/pretrain/train_stance_pilot.py`、`tools/package_stance_pilot.py`。
- 本地推理设备：CUDA，具体 GPU 型号未在本次输出单独记录；Python 使用原项目 `.venv`。测试时 PyTorch 报 `norm_first` 使 nested tensor 优化未启用的警告，不影响本轮测试退出码。
- 来源 v1 契约 SHA-256：`9bbf2893d461290371c2cefdf54eeb201b09cf639f50ea0dd0254bcc2f9eae9d`；旧权重 SHA-256：`fc5cb84b737d0bb0e9e87fd2bad423388cb52aa03822fe657627a9f9b4fcd436`。
- 有效 v2 索引（仅本机）：`E:\AIAnimationSystemData\prepared\stance_root_pose_v2_p0_20260928_r2`；契约 SHA-256：`41436aaa999486212ae1bb1d955578f7cb5618ff59e95219cef13152a2a110a9`；窗口索引 SHA-256：`66a3510bc4364f65f28506f08b09b08722ce8d6f4aca3d8681547c02192ee27b`。
- 四条明确过渡动作：原来源训练分区 3 条，测试分区 1 条。v2 的 42 个训练窗口、14 个测试窗口中，未来覆盖暂定过渡区间的分别为 13 和 5 个；无独立验证来源。后续试验拟从训练侧留出 clip 429 作验证，训练只用 226 与 227，测试 430 仍留出。
- 未提交的大文件：旧权重位于 `E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_hybrid12\epoch_012.pt`；实际通过本地 Chrome 上传的训练包为 `E:\AIAnimationSystemData\staging\motionweaver-stance-pilot-20260928-r2.tar.gz`，35,975,791 字节，SHA-256 `cc9fc1fd3a0f19553ced915265744d27771b340bba6f57e4b154545c2a208125`。云端 `/workspace/motionweaver-stance-pilot-20260928-r2.tar.gz` 的 SHA-256 一致；包内含四条原始 NPZ、原契约与统计量、旧权重和本轮代码。
- 云端产物已通过本地 Chrome 下载并存放 `E:\AIAnimationSystemData\training_runs\stance_pilot_20260928_cloud`。结果压缩包 SHA-256 `c7f775642ce345c8e8df6c12822773edcc7cae1f86f7c2cf515b4ba6fc0e5819` 与云端一致；`run_b1/best.pt` SHA-256 `317e0a5cbfeaeb2f9ae780087256ad4a267238f74bc59b90d09bd85f129a9c52`。原始 `config.json`、`metrics.jsonl` 保存在同目录。

实际命令（项目根目录，输出目录新建）：

```powershell
& 'D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe' -m data.tools.build_stance_motion_index --base-contract 'E:\AIAnimationSystemData\freezes\reference_guided_root_pose_v1_20260924\contract' --annotations 'data\annotations\stance_transition_p0_provisional.json' --output 'E:\AIAnimationSystemData\prepared\stance_root_pose_v2_p0_20260928_r2'
& 'D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe' -m training.evaluation.evaluate_stance_transition --checkpoint 'E:\AIAnimationSystemData\training_runs\conditioned_pose_20260925_hybrid12\epoch_012.pt' --stance-contract 'E:\AIAnimationSystemData\prepared\stance_root_pose_v2_p0_20260928_r2' --split test --output 'docs\experiments\assets\2026-09-28-stance-transition-v2\b0_test.json'
& 'D:\AILocomotonSystem\GR00T-WholeBodyControl\.venv\Scripts\python.exe' -m unittest discover -s tests -p test_stance_motion.py -v
```

## 结果与证据

| 指标或观察 | 保持最后姿态 | 旧模型 B0 | 口径与范围 | 证据 |
| --- | ---: | ---: | --- | --- |
| 未来覆盖过渡的关节欧氏 RMSE | 28.72 cm | 28.05 cm | 测试分区唯一 clip 430 的 5 个重叠窗口先各自求 RMSE，再等权平均；无参考，原动作未来 Root | [原始报告](assets/2026-09-28-stance-transition-v2/b0_test.json) |

B0 原始报告 SHA-256：`49cd195078c004037c85954c2ef5d6fea9776ea0af05615edc1859ae1170fa10`。3 项聚焦单测通过：早期历史/未来不泄漏、契约哈希和非法窗口拒绝、状态嵌入为零时新模型数值等于旧模型。

### B1 云端训练与本地冻结测试

最初启动 RTX40 与 A800 均返回资源不足；后来重试现有 RTX40 实例 `cpod-1vo9vxmd76ya` 成功，识别为 NVIDIA GeForce RTX 4090 24,564 MiB。通过用户本机 Chrome 的实例文件管理上传训练包，在实例终端核对 SHA-256 后解包。实例预设 2026-09-28 18:37 定时关机；产物下载后手动关机，控制台显示 `成功：1 失败：0` 且该实例状态为`关机`。A800 保持关机。未核实本实例实际费率或结算金额。

云端基础镜像的 `motionbricks` 包来自已有 `/workspace/code`；与上传包的 `data/runtime/unreal_dataset.py` SHA-256 一致。尝试 `pip install -e bundle/project --no-deps` 失败，因为仓库现有 `setup.py` 仍引用不存在的 `training/models/vqvae` 目录。因此本轮以 `PYTHONPATH=/workspace/stance_pilot_20260928/bundle/project` 运行新代码，同时复用实例已安装且对应源码哈希一致的基础包。此打包缺口需单独修复，不应声称训练包可在全新环境直接安装。

云端先执行 `--dry-run --allow-provisional`，核对完整契约、来源文件、训练/验证首批和 CUDA 前向，确认未建输出；随后以 seed 42、batch 8、学习率 5e-5 微调 8 轮。训练片段仅 226、227，原训练侧留出 clip 429 验证（14 个窗口，4 个覆盖过渡）；clip 430 的冻结测试数据未参与调参。验证过渡窗口的均值从第 1 轮 25.75 cm 降至第 8 轮 21.43 cm，选择第 8 轮权重。此值不能直接与 B0 的 **测试** 值比较。

实际云端训练命令（预检时在末尾加 `--dry-run`，预检无输出目录）：

```bash
PYTHONPATH=/workspace/stance_pilot_20260928/bundle/project python -m training.pretrain.train_stance_pilot \
  --stance-contract /workspace/stance_pilot_20260928/bundle/stance \
  --base-contract-override /workspace/stance_pilot_20260928/bundle/base \
  --source-override /workspace/stance_pilot_20260928/bundle/source \
  --initialize-from /workspace/stance_pilot_20260928/bundle/weights/parent.pt \
  --output /workspace/stance_pilot_20260928/run_b1 \
  --allow-provisional --epochs 8
```

本地使用下载的 `best.pt`，在同一个 clip 430 上无参考、原动作未来 Root 推理，对照均用同一窗口、同一权重来源契约和同一关节欧氏 RMSE 口径：

| 冻结测试范围 | 保持姿态 | 旧模型 B0 | 状态条件 B1 | 证据 |
| --- | ---: | ---: | ---: | --- |
| 5 个未来覆盖暂定过渡的窗口 | 28.72 cm | 28.05 cm | **19.04 cm** | [逐窗对比](assets/2026-09-28-stance-transition-v2/b1_test.json) |
| 全部 14 个索引窗口 | 12.87 cm | 12.24 cm | **9.31 cm** | [逐窗对比](assets/2026-09-28-stance-transition-v2/b1_test_all.json) |
| 9 个未来不含过渡的窗口 | 4.07 cm | **3.46 cm** | 3.91 cm | 从全部窗口报告筛选 `transition_frames == 0` |

两个逐窗报告 SHA-256 分别为 `81ce7205ad376aef03f411a6bb91a18996a90fc845ec6229e840fb81c0d6fe6c` 和 `6f1f22bba61e7bbd04a426261037a8c4fd0b2724025f7ab527ec744cdc34e717`。B1 在早期过渡改进明显，但稳态约退化 0.45 cm。只有一个冻结测试动作且窗口重叠，不能视为广泛泛化或统计显著结果。状态条件仍是从来源动作推定的目标代理，不是用户按钮或 CMC 实际批准状态。

本地逐窗复测使用 `training.evaluation.evaluate_stance_transition`，旧权重为上述 `epoch_012.pt`，新权重为下载的 `run_b1/best.pt`，索引为 `_r2` 目录，参数 `--split test --pilot-checkpoint ...`；全部窗口报告另加 `--selection all`。推理只在本地 CUDA 执行，云端未运行冻结测试评估。

第一次生成的 `E:\AIAnimationSystemData\prepared\stance_root_pose_v2_p0_20260928` 在修正“第 0 帧既作为输入又作为未来目标”的泄漏前产生，仅含 `contract.json` 与 `windows.jsonl`，**已废弃，禁止训练使用**；修正版为上述 `_r2` 目录。本轮尝试删除废弃目录时被执行策略拒绝，未继续删除。

## 结论与使用边界

- **直接测得：**修正版早期窗口让旧动作过渡进入真实未来帧；旧模型在唯一测试动作的早期过渡上仅比保持姿态略好，且部分单窗口更差。
- **工程推断：**下一轮应优先增加独立站蹲动作和稳态保护/门控，避免仅凭早期过渡收益接入玩家；小样本很可能只学到特定动作风格。
- **尚未验证：**真实玩家请求与 CMC 批准、在线 Root 计划、起身碰撞拒绝、循环重规划、骨长/FK、脚锁、IK、UE 蒙皮、联机同步和泛化。此数据中只有三条训练过渡，不能作为完整站蹲模型的训练结论。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-09-28 | 建立 v2 早期过渡索引并完成 B0 本地诊断；记录云端资源不足 | 索引、测试和原始评估报告 |
| 2026-09-28 | RTX 4090 云端 B1 训练、下载权重、本地冻结测试复测及关机 | 云端 `config.json`/`metrics.jsonl`、结果包哈希、B1 逐窗报告与控制台关机状态 |
