"""
overlay_popup.py — WinRemote Agent 远程控制提示小窗 V1.0
========================================================
悬浮提示窗：AStrBot 连接后自动弹出，断开后自动消失。
功能：连接状态提示 + 实时日志下拉框 + 一键断开。
实现：纯 tkinter，Windows 自带的 Python 即可运行，无需额外安装。
"""

from __future__ import annotations

import datetime
import os
import queue
import threading
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import ttk
from typing import Any

# ruff: noqa: D101 (docstring not required for private methods in this simple GUI)

LOG_DIR = Path(__file__).parent / "agent_stdout.log"
MAX_LOG_LINES = 200  # 内存保留行数


class OverlayPopup:
    """悬浮提示窗 —— 通过独立线程运行，不阻塞主 agent 循环。"""

    COLOR = {
        "bg": "#FFF0F5",        # 粉白底
        "accent": "#FF69B4",    # 热粉
        "text": "#4A4A4A",      # 深灰字
        "green": "#7BC67E",     # 成功绿
        "red": "#FF6B6B",       # 断开红
        "yellow": "#FFD93D",    # 警告黄
    }

    def __init__(self, agent_id: str):
        self._agent_id = agent_id
        self._connected_at = datetime.datetime.now()
        self._running = False
        self._disconnect_callback = None  # 主人可设置
        self._root: tk.Tk | None = None
        self._log_cache = deque(maxlen=LOG_LINES)
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._log_watcher_running = False
        self._txt_log: tk.Text | None = None
        self._thread: threading.Thread | None = None

    # ──────── 公开 API ────────

    def set_disconnect_callback(self, cb):
        """设置「断开」按钮回调。"""
        self._disconnect_callback = cb

    def show(self):
        """在独立线程中启动弹窗。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._tk_main, daemon=True)
        self._thread.start()

    def close(self):
        """安全关闭弹窗。"""
        if not self._running:
            return
        self._running = False
        self._log_watcher_running = False
        try:
            if self._root:
                self._root.after(0, self._root.destroy)
        except Exception:
            pass

    def add_log(self, line: str):
        """外部推入一条日志。"""
        self._log_queue.put(line)

    # ──────── 内部 ────────

    def _tk_main(self):
        self._root = tk.Tk()
        self._root.title("🍬 米酱在这里喵~")
        self._root.configure(bg=self.COLOR["bg"])
        self._root.resizable(True, True)
        self._root.minsize(320, 160)
        self._root.geometry("360x200+50+50")
        self._root.protocol("WM_DELETE_WINDOW", self._on_disconnect)

        # 置顶
        self._root.attributes("-topmost", True)
        # 尝试半透明 (Windows 10+)
        try:
            self._root.attributes("-alpha", 0.92)
        except Exception:
            pass

        # ── 头部 ──
        header = tk.Frame(self._root, bg=self.COLOR["accent"], height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        lbl = tk.Label(
            header,
            text=f"🐱 米酱已连接到 {self._agent_id} 喵～",
            font=("Microsoft YaHei", 11, "bold"),
            fg="white",
            bg=self.COLOR["accent"],
        )
        lbl.pack(side=tk.LEFT, padx=12, pady=12)

        # ── 连接时长 ──
        self._duration_var = tk.StringVar(value="00:00:00")
        dur_lbl = tk.Label(
            self._root,
            textvariable=self._duration_var,
            font=("Consolas", 12),
            fg=self.COLOR["text"],
            bg=self.COLOR["bg"],
        )
        dur_lbl.pack(pady=(8, 2))
        self._tick_duration()

        # ── 日志下拉框 ──
        log_frame = tk.Frame(self._root, bg=self.COLOR["bg"])
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 4))

        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._txt_log = tk.Text(
            log_frame,
            font=("Consolas", 9),
            fg=self.COLOR["text"],
            bg="white",
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            relief=tk.FLAT,
            borderwidth=0,
        )
        self._txt_log.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._txt_log.yview)
        self._txt_log.insert(tk.END, "📋 日志就绪，等待指令...\n")
        self._txt_log.config(state=tk.DISABLED)

        # ── 底部按钮 ──
        footer = tk.Frame(self._root, bg=self.COLOR["bg"])
        footer.pack(fill=tk.X, padx=10, pady=(4, 8))

        btn_disconnect = tk.Button(
            footer,
            text="🔌 断开连接",
            bg=self.COLOR["red"],
            fg="white",
            font=("Microsoft YaHei", 10),
            relief=tk.FLAT,
            activebackground="#E55555",
            command=self._on_disconnect,
            cursor="hand2",
        )
        btn_disconnect.pack(side=tk.RIGHT, padx=4)

        btn_hide = tk.Button(
            footer,
            text="👀 最小化",
            bg="#C0C0C0",
            fg="white",
            font=("Microsoft YaHei", 9),
            relief=tk.FLAT,
            command=lambda: self._root.iconify() if self._root else None,
            cursor="hand2",
        )
        btn_hide.pack(side=tk.RIGHT, padx=4)

        # ── 启动日志轮询 ──
        self._log_watcher_running = True
        self._flush_logs()
        # 也看看文件日志
        self._watch_file_log()

        self._root.mainloop()
        self._root = None

    def _tick_duration(self):
        if not self._running or not self._root:
            return
        delta = datetime.datetime.now() - self._connected_at
        total = int(delta.total_seconds())
        h, m, s = total // 3600, (total % 3600) // 60, total % 60
        self._duration_var.set(f"⏱️ 已连接 {h:02d}:{m:02d}:{s:02d}")
        self._root.after(1000, self._tick_duration)

    def _on_disconnect(self):
        if self._disconnect_callback:
            self._disconnect_callback()
        self.close()

    def _flush_logs(self):
        if not self._running or not self._root or not self._txt_log:
            return
        try:
            while True:
                line = self._log_queue.get_nowait()
                self._log_cache.append(line)
        except queue.Empty:
            pass

        if self._log_cache:
            self._txt_log.config(state=tk.NORMAL)
            self._txt_log.delete("1.0", tk.END)
            self._txt_log.insert(tk.END, "\n".join(self._log_cache))
            self._txt_log.see(tk.END)
            self._txt_log.config(state=tk.DISABLED)

        self._root.after(800, self._flush_logs)

    def _watch_file_log(self):
        """读取 agent_stdout.log 的最后 20 行推入日志缓存。"""
        if not self._log_watcher_running or not LOG_DIR.exists():
            return
        try:
            text = Path(LOG_DIR).read_text(encoding="utf-8", errors="replace")
            lines = text.strip().splitlines()[-20:]
            for line in lines:
                self.add_log(line.rstrip()[:120])
        except Exception:
            pass
        if self._log_watcher_running and self._root:
            self._root.after(3000, self._watch_file_log)  # 每 3 秒刷新


# ──────── 便捷工厂 ────────

_shown_popups: dict[str, OverlayPopup] = {}


def show_popup(agent_id: str, on_disconnect: callable | None = None) -> OverlayPopup:
    """在 agent 连接成功后调用。"""
    if agent_id in _shown_popups:
        _shown_popups[agent_id].close()
    popup = OverlayPopup(agent_id)
    if on_disconnect:
        popup.set_disconnect_callback(on_disconnect)
    popup.show()
    _shown_popups[agent_id] = popup
    return popup


def close_popup(agent_id: str):
    """在 agent 断开时调用。"""
    popup = _shown_popups.pop(agent_id, None)
    if popup:
        popup.close()


def add_log_to_popup(agent_id: str, msg: str):
    """向指定弹窗推日志。"""
    popup = _shown_popups.get(agent_id)
    if popup:
        popup.add_log(msg)