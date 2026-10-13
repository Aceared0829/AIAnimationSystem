"""历史导入兼容入口；模型实现与新配置均使用 MotionWeaver。"""

import sys

from motionweaver.legacy import LegacyModuleAliases

sys.meta_path.insert(0, LegacyModuleAliases())
