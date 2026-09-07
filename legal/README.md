# 许可文件来源与核对记录

> **新增说明：** 本文件由 AIAnimationSystem 派生项目于 2026-09-07 编写；下列第三方原文文件没有加入本项目的改写。

## 完整许可文本

| 文件 | 来源与用途 |
| --- | --- |
| [Apache-2.0.txt](Apache-2.0.txt) | 2026-09-07 从 [Apache 官方全文](https://www.apache.org/licenses/LICENSE-2.0.txt) 下载，保留原始字节；包含第 1–9 条、结束标记及附录。 |
| [NVIDIA-Open-Model-License-2025-10-24.pdf](NVIDIA-Open-Model-License-2025-10-24.pdf) | 2026-09-07 从 [NVIDIA 官网的 PDF 下载链接](https://www.nvidia.com/content/dam/en-zz/Solutions/license-agreements/enterprise-software/nvidia-open-model-license-agreements-24-10-2025.pdf) 获取，保留原始字节；对应 [官方页面](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/) 的 2025-10-24 版。 |

根 [LICENSE](../LICENSE) 继承自上游，本次保持原样。它不是以上两个协议的完整、逐字副本：Apache 部分为简短声明；NVIDIA 部分与官网的第 3.1 条等条款存在文字差异。这里提供官方原文供阅读和随适用材料分发，不删除继承的历史声明，也不自行重写协议条款。

## 从上游历史恢复的文件

共同祖先与本地 `origin/main` 在本次核对时均为 [`4141c34280abb67c82e115342a8720f4a83d750d`](https://github.com/NVlabs/GR00T-WholeBodyControl/commit/4141c34280abb67c82e115342a8720f4a83d750d)。该提交也已在 NVlabs 官方仓库核实。以下文件直接从该 Git 对象恢复，文件字节与原对象一致：

- [Apache License - GEAR-SONIC.txt](<Apache License - GEAR-SONIC.txt>)
- [THIRD-PARTY SOFTWARE NOTICES - GEAR-SONIC.txt](<THIRD-PARTY SOFTWARE NOTICES - GEAR-SONIC.txt>)
- [THIRD-PARTY SOFTWARE NOTICES AND ASSET LICENSES - GEAR-SONIC.txt](<THIRD-PARTY SOFTWARE NOTICES AND ASSET LICENSES - GEAR-SONIC.txt>)

这些文件此前在 `cda82b3` 的游戏动画精简中被删除。本次恢复仅为保留原来的版权及第三方来源信息，不恢复机器人实现。

文件名中的 GEAR-SONIC 保持原样。其内容适用范围须结合实际继承或分发的组件判断，不能据此认定 unitree_sdk2_python、XRoboToolkit、robosuite、tpm、BeyondMimic 都仍包含在当前发布包中。它们也不是当前 MotionBricks、UE 集成及 Python 依赖的完整物料清单。

历史 `Apache License - GEAR-SONIC.txt` 自身是经过缩写的文本；历史第三方文件中标为“FULL LICENSE TEXTS”的段落也不能据该标题认定完整。保留它们不表示采用这些缩写替代官方协议。Apache 完整文本见本目录 `Apache-2.0.txt`；若未来重新分发相关第三方组件，须从该组件实际来源保留它适用的完整许可证与通知。

## 本次验证及边界

- 根 `LICENSE` 与共同祖先内容一致，本次没有修改。
- 三个恢复文件与固定提交的 Git blob 逐字节一致。
- 官方 Apache 文本包含完整结束标记和附录；官方 NVIDIA PDF 从其协议网页直接链接下载，文件以 `%PDF-` 开头，并已核对在线的两页文本。
- 根 [NOTICE](../NOTICE) 包含 NVIDIA 第 3.1 条指定的署名原文。
- [CITATION.cff](../CITATION.cff) 的原 MotionBricks `preferred-citation` 保持原题名、16 位原论文作者和论文链接；顶层只标识本派生项目维护账号。

以下 SHA-256 用于复核这次获取的文件，不表示完成全部第三方权利审查：

| 文件 | SHA-256 |
| --- | --- |
| `../LICENSE` | `4a511782076bfc70db332436c08fc51a60403f66dddd191ce8d6269995f58408` |
| `Apache-2.0.txt` | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `NVIDIA-Open-Model-License-2025-10-24.pdf` | `4d2fb590aa9b30c47f2058bff17291df7fa2aa0c1bd775a20703da9bb267cfab` |
| `Apache License - GEAR-SONIC.txt` | `4d42f1db12bb3b31150f735fdb3e18f40c7984f50f17bcad783e9bb5251e74b7` |
| `THIRD-PARTY SOFTWARE NOTICES - GEAR-SONIC.txt` | `f88d3638f4eee9e3f3e52c13eccca950755cbaaae4e9923a2d45435b2574d3be` |
| `THIRD-PARTY SOFTWARE NOTICES AND ASSET LICENSES - GEAR-SONIC.txt` | `23fb2ecf02259d8fc78850e4f1466d44e01fbe514c5f2ffbab0578bd0054f0e0` |

根 NOTICE 和这份来源记录不能替代 Apache 第 4(b) 条要求的被修改文件中的醒目修改说明。本次为相对记录上游版本已修改的继承文本文件补齐修改标记；Python AST/有效 token、XML 解析树、Git 有效规则验证未变。网格、演示媒体、训练数据和依赖版本尚未完成逐项全面的权利审查；后续实际分发仍应以包含的材料为范围继续核对。
