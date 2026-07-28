"""MotionBricks 交互演示的简体中文控制面板。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk
import ctypes
from ctypes import wintypes
import os
import platform
import time


class ChineseControlPanel:
    """在独立窗口中提供线程安全的中文演示控制。"""

    def __init__(self) -> None:
        self._commands: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
        self._closed = threading.Event()
        self._paused = threading.Event()
        self._host_ready = threading.Event()
        self._render_host_hwnd = 0
        self._mujoco_hwnd = 0
        self._thread = threading.Thread(target=self._run, name="MotionBricks中文控制台", daemon=True)
        self._thread.start()

    @property
    def is_closed(self) -> bool:
        return self._closed.is_set()

    @property
    def is_paused(self) -> bool:
        return self._paused.is_set()

    def poll_commands(self) -> list[tuple[str, object]]:
        """取出界面线程发来的全部待处理命令。"""
        commands = []
        while True:
            try:
                commands.append(self._commands.get_nowait())
            except queue.Empty:
                return commands

    def close(self) -> None:
        self._closed.set()

    def embed_mujoco_window(self, timeout: float = 10.0) -> bool:
        """在 Windows 上把 MuJoCo 渲染窗口嵌入中文主窗口。"""
        if platform.system() != "Windows" or not self._host_ready.wait(timeout):
            return False

        user32 = ctypes.windll.user32
        target_pid = os.getpid()
        matches: list[int] = []
        enum_callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_callback(hwnd, _lparam):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != target_pid or not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, length + 1)
            if title_buffer.value.startswith("MuJoCo"):
                matches.append(int(hwnd))
                return False
            return True

        deadline = time.time() + timeout
        callback = enum_callback_type(enum_callback)
        while time.time() < deadline and not matches:
            user32.EnumWindows(callback, 0)
            if not matches:
                time.sleep(0.1)
        if not matches:
            return False

        hwnd = matches[0]
        get_window_long = user32.GetWindowLongPtrW
        set_window_long = user32.SetWindowLongPtrW
        get_window_long.restype = ctypes.c_ssize_t
        set_window_long.restype = ctypes.c_ssize_t
        style_index = -16
        ws_caption = 0x00C00000
        ws_thickframe = 0x00040000
        ws_popup = 0x80000000
        ws_child = 0x40000000
        style = get_window_long(hwnd, style_index)
        style = (style & ~ws_caption & ~ws_thickframe & ~ws_popup) | ws_child
        set_window_long(hwnd, style_index, style)
        user32.SetParent(hwnd, self._render_host_hwnd)
        self._mujoco_hwnd = hwnd
        client_rect = wintypes.RECT()
        user32.GetClientRect(self._render_host_hwnd, ctypes.byref(client_rect))
        user32.MoveWindow(
            hwnd,
            0,
            0,
            max(1, client_rect.right - client_rect.left),
            max(1, client_rect.bottom - client_rect.top),
            True,
        )
        user32.ShowWindow(hwnd, 5)
        return True

    def _toggle_pause(self) -> None:
        if self._paused.is_set():
            self._paused.clear()
        else:
            self._paused.set()

    def _run(self) -> None:
        root = tk.Tk()
        root.title("MotionBricks G1 中文交互演示")
        root.geometry("1500x850")
        root.minsize(1100, 650)

        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        main = ttk.Frame(root, padding=14, width=420)
        main.grid(row=0, column=0, sticky=tk.NSEW)
        main.grid_propagate(False)

        render_host = tk.Frame(root, background="#182c3d", highlightthickness=0)
        render_host.grid(row=0, column=1, sticky=tk.NSEW)
        root.update_idletasks()
        self._render_host_hwnd = render_host.winfo_id()
        self._host_ready.set()

        title = ttk.Label(main, text="MotionBricks G1 交互演示", font=("Microsoft YaHei UI", 15, "bold"))
        title.pack(anchor=tk.W, pady=(0, 6))

        status_var = tk.StringVar(value="运行中")
        ttk.Label(main, textvariable=status_var, foreground="#1976d2").pack(anchor=tk.W, pady=(0, 12))

        run_group = ttk.LabelFrame(main, text="运行控制", padding=10)
        run_group.pack(fill=tk.X, pady=5)
        ttk.Button(run_group, text="暂停 / 继续", command=self._toggle_pause).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(run_group, text="重置角色", command=lambda: self._commands.put(("reset", True))).grid(
            row=0, column=1, padx=4, pady=4
        )
        ttk.Button(run_group, text="退出演示", command=self.close).grid(row=0, column=2, padx=4, pady=4)

        camera_group = ttk.LabelFrame(main, text="相机视角", padding=10)
        camera_group.pack(fill=tk.X, pady=5)
        camera_presets = (
            ("正面", (90.0, -15.0, 3.5)),
            ("背面", (-90.0, -15.0, 3.5)),
            ("左侧", (180.0, -15.0, 3.5)),
            ("右侧", (0.0, -15.0, 3.5)),
            ("俯视", (90.0, -80.0, 4.5)),
        )
        for index, (label, preset) in enumerate(camera_presets):
            ttk.Button(
                camera_group,
                text=label,
                command=lambda value=preset: self._commands.put(("camera", value)),
            ).grid(row=index // 3, column=index % 3, padx=4, pady=4, sticky=tk.EW)
        for column in range(3):
            camera_group.columnconfigure(column, weight=1)

        display_group = ttk.LabelFrame(main, text="显示选项", padding=10)
        display_group.pack(fill=tk.X, pady=5)
        contact_var = tk.BooleanVar(value=False)
        joint_var = tk.BooleanVar(value=False)
        transparent_var = tk.BooleanVar(value=False)

        def send_display() -> None:
            self._commands.put(
                (
                    "display",
                    {
                        "contact": contact_var.get(),
                        "joint": joint_var.get(),
                        "transparent": transparent_var.get(),
                    },
                )
            )

        ttk.Checkbutton(display_group, text="显示接触点", variable=contact_var, command=send_display).pack(anchor=tk.W)
        ttk.Checkbutton(display_group, text="显示关节", variable=joint_var, command=send_display).pack(anchor=tk.W)
        ttk.Checkbutton(display_group, text="半透明显示", variable=transparent_var, command=send_display).pack(anchor=tk.W)

        help_group = ttk.LabelFrame(main, text="键盘操作", padding=10)
        help_group.pack(fill=tk.BOTH, expand=True, pady=5)
        help_text = (
            "移动\n"
            "  W / A / S / D：前进、左移、后退、右移\n\n"
            "动作风格\n"
            "  V：慢走    Z：手部支撑爬行\n"
            "  X：拳击式行走    B：肘部支撑爬行\n"
            "  R：潜行    T：受伤行走\n"
            "  C：蹲伏潜行    E：快乐舞步\n"
            "  F：僵尸行走    G：持枪行走\n"
            "  Q：惊恐行走\n\n"
            "鼠标\n"
            "  右键拖动：旋转相机\n"
            "  滚轮：拉近或拉远"
        )
        ttk.Label(
            help_group,
            text=help_text,
            justify=tk.LEFT,
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor=tk.NW)

        def process_status() -> None:
            status_var.set("已暂停" if self._paused.is_set() else "运行中")
            if not self._closed.is_set():
                root.after(100, process_status)
            else:
                root.destroy()

        def on_close() -> None:
            self.close()

        def resize_embedded_viewer(event) -> None:
            if self._mujoco_hwnd and platform.system() == "Windows":
                ctypes.windll.user32.MoveWindow(
                    self._mujoco_hwnd,
                    0,
                    0,
                    max(1, event.width),
                    max(1, event.height),
                    True,
                )

        render_host.bind("<Configure>", resize_embedded_viewer)
        root.protocol("WM_DELETE_WINDOW", on_close)
        root.after(100, process_status)
        root.mainloop()
