"""
__init__.py — 薄壳（V0.9.0）
==========================
唯一职责：让 `from astrbot_plugin_winremote import ...` 可用。
真实逻辑全部在 astrbot_plugin_winremote.py（与目录同名，AstrBot 入口）。

实现方式：直接 exec 主模块源码到当前命名空间。
这样做的好处：
1. 没有循环 import（不触发父包的 __getattr__）
2. 所有公共符号都在 __all__ 里
3. ruff / IDE 都能正确识别
"""

__is_shell__ = True

# 显式导出列表
__all__ = [
    "__version__",
    "VERSION",
    "PLUGIN_NAME",
    "DANGEROUS_KEYWORDS",
    "INJECTION_CHARS",
    "MAX_OUTPUT_BYTES",
    "STREAM_CHUNK_SIZE",
    "STREAM_INTERVAL",
    "HEARTBEAT_INTERVAL",
    "HEARTBEAT_TIMEOUT",
    "AUDIT_MAX",
    "AgentConnection",
    "AgentManager",
    "PasswordGuard",
    "AuditLogger",
    "WinRemoteServer",
    "WinRemotePlugin",
    "get_config",
    "validate_command",
    "validate_path",
    "websockets",
    "ConnectionClosed",
    "_HAS_WS",
    "_HAS_ASTRBOT",
    "register",
    "StarTools",
    "StarHandlerMetadata",
    "StarHandlerType",
    "EventType",
    "CommandType",
    "AstrBotConfig",
    "logger",
]

# 直接读取并 exec 主模块源码
# 这样做完全避免了 import 循环：
# - 不触发父包 __getattr__
# - 不触发 astrbot_plugin_winremote.py 里的 `from astrbot_plugin_winremote import`
# - 主模块里的 `from astrbot_plugin_winremote import (...)` 会找到已经部分初始化的本模块
import os

_THIS_DIR = os.path.dirname(__file__)
_MAIN_PATH = os.path.join(_THIS_DIR, "astrbot_plugin_winremote.py")

with open(_MAIN_PATH, encoding="utf-8") as _f:
    _MAIN_SOURCE = _f.read()

# 先预置 __version__ 别名，让主模块的 `from astrbot_plugin_winremote import __version__`
# 能找到（虽然主模块实际用的是 VERSION，但 __all__ 里暴露了 __version__）
# 执行主模块源码，命名空间就是当前模块的 globals()
exec(compile(_MAIN_SOURCE, _MAIN_PATH, "exec"), globals())

# 主模块执行完后，创建 __version__ 别名
__version__ = VERSION  # noqa: F821 (VERSION 由 exec 注入)
