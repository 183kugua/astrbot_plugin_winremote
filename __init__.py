"""
__init__.py — 薄壳（V0.9.9）
==================================
唯一职责：让 `from astrbot_plugin_winremote import ...` 可用。
真实逻辑全部在 astrbot_plugin_winremote.py（与目录同名，AStrBot 入口）。

V0.9.9 变更：
- LLM Tool 注册（add_llm_tools，v4.5.7+ 推荐方式）
- Skill 技能包自动加载（skills/winremote-remote-control/）
- /win --llm 降级通道（LLM 不可用时退回传统指令）
- on_llm_response 钩子（回复中追加授权状态）

实现方式：标准 import 导入主模块符号到当前命名空间。
这样既避免了 exec() 带来的安全审计风险，又保持了完整的公共 API 导出。
"""

from typing import Any

__is_shell__ = True

from typing import Any

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

# 正常导入主模块，不使用 exec
# 主模块 (astrbot_plugin_winremote.py) 内部不依赖包级别导入，
# 子模块 (tool_handlers.py) 中的 from astrbot_plugin_winremote import ...
# 使用延迟导入，不会造成循环依赖
from .astrbot_plugin_winremote import (
    __version__,
    VERSION,
    PLUGIN_NAME,
    DANGEROUS_KEYWORDS,
    INJECTION_CHARS,
    MAX_OUTPUT_BYTES,
    STREAM_CHUNK_SIZE,
    STREAM_INTERVAL,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    AUDIT_MAX,
    AgentConnection,
    AgentManager,
    PasswordGuard,
    WinRemoteServer,
    WinRemotePlugin,
    get_config,
    validate_command,
    validate_path,
)

# websockets 条件导入
try:
    import websockets
    from websockets.exceptions import ConnectionClosed
    _HAS_WS = True
except ImportError:
    websockets = None  # type: ignore[assignment]
    ConnectionClosed = None  # type: ignore[assignment]
    _HAS_WS = False

# AStrBot 条件导入
try:
    from astrbot.api.all import (
        StarTools,
        StarHandlerMetadata,
        StarHandlerType,
        EventType,
        AstrBotConfig,
    )
    from astrbot.api.message_components import CommandType
    import astrbot.api.logger as logger

    _HAS_ASTRBOT = True
except ImportError:
    StarTools = None  # type: ignore[assignment]
    StarHandlerMetadata = None  # type: ignore[assignment]
    StarHandlerType = None  # type: ignore[assignment]
    EventType = None  # type: ignore[assignment]
    CommandType = None  # type: ignore[assignment]
    AstrBotConfig = None  # type: ignore[assignment]

    import logging
    logger = logging.getLogger("astrbot_plugin_winremote")

    _HAS_ASTRBOT = False


# register 函数（AStrBot 入口）
def register(tools: Any = None) -> Any | None:
    """
    注册函数 — AStrBot 入口。
    如果主模块加载成功，调用其 register()。
    """
    try:
        return WinRemotePlugin(tools=tools)  # noqa: F821 (已由上方 import 注入)
    except Exception:
        return None