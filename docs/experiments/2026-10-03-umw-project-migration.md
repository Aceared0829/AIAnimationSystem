# UMWSamplePreview 项目迁移与 CR 回归

| 字段 | 内容 |
| --- | --- |
| 实验 ID / 类型 | `2026-10-03-umw-project-migration`；UE 迁移 / 默认场景回归 |
| 时间与状态 | 2026-10-03，Asia/Hong_Kong；完成本页列出的检查 |
| 执行者 | 本项目维护过程中的本机工具验证 |
| 代码 | 初始迁移 `0cc1b17`；最终源码 `8f5b927`；迁移验证使用 dirty 工作树，相关范围为项目 Source、Config、uproject 与两个 MotionWeaver 目录；最终构建覆盖 CR 后代码 |
| 环境 | Windows、Win64 Development、本机 `D:/UE_5.8` UE 5.8.3；工具回归使用 UE 附带 Python 3.11.8、PowerShell、Node.js |

## 问题、对照与资产身份

将 MotionMatchingInCpp 的 Gameplay 与 Content 迁入项目模块，同时保留默认场景效果，移除旧插件和未使用的角色/控制器空壳。对照为移动前的原插件项目；原生模块路径、资产挂载与 API 宏是变化因素。验证要求为文件无缺失、资产可加载、蓝图可编译、默认类/参数/关卡 Actor 一致，以及 PIE 移动与蹲伏仍工作。

原插件描述文件标注作者 Acceered，迁入源码保留已有版权信息。Content 2992 文件、4,656,809,342 字节属于本机既有资产；移动前后 SHA-256 一致，随后通过 UE 原生重存和蓝图编译更新包引用。资产与备份未发布；其他机器需要自行恢复与源码匹配且合法可用的 Content，干净检出不能运行默认地图。[迁移说明](../../unreal-sample/UMWSamplePreview/MOTIONMATCHING_MIGRATION.md)记录了目录、兼容重定向、依赖及完整验证边界。

## 命令与证据

在仓库根目录执行最终构建与源码工具回归：

```powershell
& D:/UE_5.8/Engine/Build/BatchFiles/Build.bat UMWSamplePreviewEditor Win64 Development -Project=D:/AILocomotonSystem/GR00T-WholeBodyControl/unreal-sample/UMWSamplePreview/UMWSamplePreview.uproject -WaitMutex -NoHotReloadFromIDE
& D:/UE_5.8/Engine/Build/BatchFiles/Build.bat UMWSamplePreview Win64 Development -Project=D:/AILocomotonSystem/GR00T-WholeBodyControl/unreal-sample/UMWSamplePreview/UMWSamplePreview.uproject -WaitMutex -NoHotReloadFromIDE
& D:/UE_5.8/Engine/Binaries/ThirdParty/Python3/Win64/python.exe -m unittest discover -s tests -p test_motion_storage_migration.py -v
& D:/UE_5.8/Engine/Binaries/ThirdParty/Python3/Win64/python.exe -m unittest discover -s tests -p test_motionweaver_sync.py -v
node --test tests/test_migration_progress_ui.cjs
& ./unreal-script/Tools/Sync-MotionWeaver.ps1 -Check
```

资产扫描、原生 ResavePackages、95 个蓝图的编译保存和 PIE 由本机 `.build/mmcpp-migration/` 中的 UE Python 脚本执行。最终 PIE 设置 `MMCPP_PHASE=cr`、`MMCPP_KEYSONLY=1`，使用 `-ExecutePythonScript=<该目录>/runtime.py -unattended -nosplash -NoSound -SCCProvider=None`，并通过 `-abslog` 记录日志。脚本调用真实 PIE，通过 Character 输入接口移动、蹲下及站起；不是人工键盘试玩。旧/新 idle、walk、crouch、stand 截图已生成并复核默认场景；渲染时序不同，不用逐帧截图或行走终点宣称完全相等。原始脚本、日志、备份和 Asset Registry 清单仅在当前机器有效。

可提交摘要为 [verification.json](assets/2026-10-03-umw-project-migration/verification.json)，包含前后对照、最终 PIE 观测、测试数量与本机原始证据 SHA-256；完整日志位于 `.build/delivery-review/`，迁移备份位于 `.build/mmcpp-migration/backup/`。这些是迁移与功能回归数据，不涉及训练分区、随机采样或模型质量指标。

## 结果与限制

| 检查 | 直接结果 |
| --- | --- |
| Editor / Game | Win64 Development 均成功；没有 Cook 或打包 |
| Asset Registry / Blueprint | 前后 2994 条记录；加载失败 0；95 个蓝图编译/保存失败 0；旧挂载/原生模块依赖 0 |
| 默认关卡与配置 | 115 个 Actor 的类和位置一致；Pawn、Controller、输入、Mesh、AnimBP、CMC 参数和原生组件一致，比较时规范化迁移路径 |
| 最终 PIE | idle/walk/crouch/stand 均有效；88 骨；角色与相机初始位置一致；native property 初始化错误 0 |
| 工具回归 | 存储 11 项、镜像 4 项、观察器界面 3 项通过；实际数据盘迁移未执行 |
| 镜像 | Sample 与 unreal-script 插件文件 SHA-256 一致；Junction、Check、WhatIf 与排除目录夹具通过 |

CR 修复了复制前删除源数据、同名目标冲突缺少检查、轻量观察器语法与 status 显示、错误响应后页面无法恢复、镜像链接边界和原生 Color 初始化问题。源码复审与上述回归未发现新的阻塞问题。

未覆盖联网、所有角色/Traversal、推理接线、UE NNE、AnimGraph 模型输出或打包性能；不能作为模型可上线或完整玩法验收。原有未使用 `CHT_RotationOffsetCurve` 缺少 Context 与多个未注册 `DDCVar.*` 的诊断仍存在，未用改变默认行为的方式掩盖。原生 Color 初始化错误已修复，原有两个 Blueprint 结构体加载错误及缺失 Foley Tag 提示在迁移处理中消失。

## 修订历史

| 日期 | 变更 | 依据 |
| --- | --- | --- |
| 2026-10-03 | 记录迁移、CR 修复与最终回归；保留原有诊断和未覆盖项 | 本机构建、UE Python/PIE、临时夹具、媒体与日志哈希 |
