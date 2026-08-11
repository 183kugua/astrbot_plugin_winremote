"""WinRemote 插件 - 导出兼容 API"""

# 版本信息
__version__ = "2.0.0-refactor"
__author__ = "mijiang"

# 延迟导入，避免测试时触发 astrbot 依赖
def __getattr__(name):
    if name == "WinRemotePlugin":
        from .plugin import WinRemotePlugin
        return WinRemotePlugin
    elif name == "WinRemoteConfig":
        from .config import WinRemoteConfig
        return WinRemoteConfig
    elif name == "AgentConnection":
        from .models import AgentConnection
        return AgentConnection
    elif name == "CommandResult":
        from .models import CommandResult
        return CommandResult
    elif name == "RemoteSession":
        from .models import RemoteSession
        return RemoteSession
    elif name == "SecurityPolicy":
        from .models import SecurityPolicy
        return SecurityPolicy
    elif name == "AuthManager":
        from .auth import AuthManager
        return AuthManager
    elif name == "WinRemoteServer":
        from .server import WinRemoteServer
        return WinRemoteServer
    elif name == "ToolHandlers":
        from .tool_handlers import ToolHandlers
        return ToolHandlers
    elif name == "get_tools_schema":
        from .tools import get_tools_schema
        return get_tools_schema
    elif name == "get_tool_names":
        from .tools import get_tool_names
        return get_tool_names
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# 兼容旧版本的导出
__all__ = [
    "WinRemotePlugin",
    "WinRemoteConfig",
    "AgentConnection",
    "CommandResult",
    "RemoteSession",
    "SecurityPolicy",
    "AuthManager",
    "WinRemoteServer",
    "ToolHandlers",
    "get_tools_schema",
    "get_tool_names"
]
