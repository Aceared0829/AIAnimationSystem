# MotionBricks 中文交互界面

本页说明 [AIAnimationSystem](../../README.md) 对上游 MotionBricks 参考演示所做的中文界面与 Windows 适配。2026-09-07 修改启动目录与迁移说明；此界面不代表 UE 运行时插件。

## 界面概览

运行交互演示：

```bash
python scripts/interactive_demo_g1.py
```

默认参数 `--chinese_ui 1` 会启用完整中文界面，并隐藏 MuJoCo 原生查看器中无法通过语言包翻译的英文左右侧栏。

### Windows 单窗口布局

Windows 版本使用一个主窗口：

```text
┌──────────────────────┬─────────────────────────────────────────┐
│ 中文控制栏           │ MuJoCo 实时 3D 画面                     │
│                      │                                         │
│ 运行控制             │ - CUDA 模型推理                         │
│ 相机视角             │ - G1 动画显示                           │
│ 显示选项             │ - 鼠标相机操作                          │
│ 键盘操作说明         │                                         │
└──────────────────────┴─────────────────────────────────────────┘
```

实现上，程序保留 MuJoCo 原生 OpenGL 渲染窗口，并通过 Win32 子窗口托管将其嵌入中文主窗口。因此不会改变动作生成、渲染性能或鼠标相机功能。

### Linux 与 macOS

单窗口嵌入依赖 Windows 的 Win32 窗口接口。Linux 和 macOS 会自动回退为两个窗口：

- MotionBricks 中文控制窗口；
- 隐藏英文侧栏的 MuJoCo 3D 窗口。

推理和操作功能不受影响。

## 中文控制栏

### 运行控制

| 控件 | 作用 |
|---|---|
| 暂停 / 继续 | 暂停或恢复动作帧生成 |
| 重置角色 | 重置生成器上下文并从初始状态重新开始 |
| 退出演示 | 关闭中文主窗口并结束演示 |

### 相机视角

| 控件 | 作用 |
|---|---|
| 正面 | 切换至角色正面视角 |
| 背面 | 切换至角色背面视角 |
| 左侧 | 切换至角色左侧视角 |
| 右侧 | 切换至角色右侧视角 |
| 俯视 | 切换至俯视视角 |

仍可直接在 3D 画面中使用鼠标：

- 右键拖动：旋转相机；
- 滚轮：拉近或拉远。

### 显示选项

| 选项 | 作用 |
|---|---|
| 显示接触点 | 显示 MuJoCo 接触位置 |
| 显示关节 | 显示关节标记 |
| 半透明显示 | 以半透明方式绘制模型 |

## 键盘操作

### 移动

| 按键 | 动作 |
|---|---|
| `W` | 向前移动 |
| `A` | 向左移动 |
| `S` | 向后移动 |
| `D` | 向右移动 |

移动方向以当前相机方向为参照。

### 动作风格

| 按键 | 动作风格 |
|---|---|
| `V` | 慢走 |
| `Z` | 手部支撑爬行 |
| `X` | 拳击式行走 |
| `B` | 肘部支撑爬行 |
| `R` | 潜行 |
| `T` | 受伤行走 |
| `C` | 蹲伏潜行 |
| `E` | 快乐舞步 |
| `F` | 僵尸行走 |
| `G` | 持枪行走 |
| `Q` | 惊恐行走 |

不按动作风格键时，没有移动输入为待机，有移动输入为普通行走。

## 启动参数

### Windows 无控制台启动器

完成 `.venv` 和模型权重配置后，可以在仓库根目录直接双击：

```text
MotionBricks.exe
```

启动器具有以下行为：

- 不显示命令行控制台；
- 自动使用仓库根目录下的 `.venv\Scripts\pythonw.exe`；
- 自动启动 `motionbricks\scripts\interactive_demo_g1.py --chinese_ui 1`；
- 以仓库内的 `motionbricks` 目录作为工作目录，确保配置和资源路径一致；
- 启动失败时显示中文错误窗口；
- 将启动结果写入仓库根目录的 `MotionBricks-launcher.log`。

`MotionBricks.exe` 需要与项目目录一起使用，它不是包含 Python、模型权重和依赖的独立安装包。启动器按相对位置查找文件，但 `.venv` 激活脚本和 editable 安装可能记录绝对路径；移动或重命名本地仓库后，需要重建或修复环境并更新快捷方式。仅修改 GitHub 仓库名称不要求移动本地目录。不要只把 EXE 单独复制到其他位置。

桌面快捷方式应指向仓库根目录的 `MotionBricks.exe`，起始位置设为仓库根目录，图标可使用：

```text
launcher\assets\motionbricks.ico
```

快捷方式属于每台电脑的本地系统配置，不提交到 Git 仓库。

### 重新构建 Windows 启动器

启动器源码位于 `launcher` 目录，使用 .NET 10 Windows Desktop 构建：

```powershell
dotnet publish launcher\MotionBricksLauncher.csproj -c Release -r win-x64 `
  --self-contained false -p:PublishSingleFile=true `
  -o launcher\publish

Copy-Item launcher\publish\MotionBricks.exe .\MotionBricks.exe -Force
```

最终 EXE 已嵌入项目图标；同一份 `.ico` 文件也用于桌面快捷方式，以保持任务栏、资源管理器和快捷方式的视觉一致性。

### 默认中文界面

```bash
python scripts/interactive_demo_g1.py
```

等价于：

```bash
python scripts/interactive_demo_g1.py --chinese_ui 1
```

### 恢复 MuJoCo 原生界面

如果需要使用 MuJoCo 原生高级调试面板：

```bash
python scripts/interactive_demo_g1.py --chinese_ui 0
```

该模式会禁用中文控制栏，并恢复 MuJoCo 原生英文左右侧栏。

### 查看全部中文命令行帮助

```bash
python scripts/interactive_demo_g1.py --help
```

项目会将 `argparse` 的用法、选项、帮助和常见参数错误设置为 UTF-8 中文输出。

## 技术边界

MuJoCo 官方 Python wheel 中的传统查看器菜单由已编译的原生扩展生成，不提供语言包接口，内置界面字体也不包含完整中文字形。因此项目没有修改虚拟环境中的第三方二进制文件，而是：

1. 隐藏原生英文左右侧栏；
2. 提供项目内维护的中文控制栏；
3. 在 Windows 上把原生 3D 渲染窗口嵌入中文主窗口；
4. 使用 `--chinese_ui 0` 保留原生调试界面的访问入口。

模型名称、骨骼名称、配置键和动作特征名仍保持英文。这些是模型检查点与程序接口的一部分，翻译后会破坏兼容性，不属于可见界面文本。

## 故障排查

### 中文界面打开后没有 3D 画面

首次加载模型可能需要十几秒。请等待日志依次出现：

```text
正在加载模型
正在加载数据集
正在运行第 1 次迭代，共 1 次……
```

如果仍无画面，先确认 CUDA：

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### Windows 上出现两个窗口

这表示 MuJoCo 窗口没有成功嵌入。请检查：

- 是否通过项目虚拟环境启动；
- 是否有上一次演示进程仍在运行；
- 安全软件是否阻止 Win32 `SetParent` 窗口托管；
- 当前 MuJoCo 版本是否与项目安装版本一致。

关闭全部演示进程后重新运行即可再次尝试嵌入。

### 需要 MuJoCo 的高级参数面板

中文控制栏只提供本项目实际使用的交互与可视化功能。MuJoCo 完整的物理参数、求解器和传感器调试面板可通过以下命令恢复：

```bash
python scripts/interactive_demo_g1.py --chinese_ui 0
```
