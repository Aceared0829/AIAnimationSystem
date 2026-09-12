"""argparse 的简体中文界面支持。"""

import argparse
import sys


_TRANSLATIONS = {
    "usage: ": "用法：",
    "options": "选项",
    "positional arguments": "位置参数",
    "optional arguments": "可选参数",
    "show this help message and exit": "显示此帮助信息并退出",
    "the following arguments are required: %s": "必须提供以下参数：%s",
    "unrecognized arguments: %s": "无法识别的参数：%s",
    "invalid choice: %(value)r (choose from %(choices)s)": "无效选项：%(value)r（请选择 %(choices)s 中的一项）",
    "expected one argument": "需要一个参数值",
}


def enable_chinese_argparse() -> None:
    """启用 argparse 中文内置文案，并尽量将标准输出切换为 UTF-8。"""
    original_translate = argparse._

    def translate(message: str) -> str:
        return _TRANSLATIONS.get(message, original_translate(message))

    argparse._ = translate

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
