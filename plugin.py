"""WinRemote 插件主入口（瘦客户端）"""
import logging
from typing import Optional
from astrbot.api import star, AstrBotConfig
from astrbot.api.event import MessageChain, MessageEvent
from astrbot.api.platform import Platform

from .config import WinRemoteConfig, DEFAULT_CONFIG_PATH
from .auth import AuthManager
from .server import WinRemoteServer
from .tool_handlers import ToolHandlers
from .tools import get_tools_schema

logger = logging.getLogger("astrbot.plugin.winremote")


@star(
    name="winremote",
    description="WinRemote 远程控制 Windows 电脑",
    version="2.0.0-refactor",
    author="mijiang"
)
class WinRemotePlugin:
    """WinRemote 插件主类"""
    
    def __init__(self, context: dict):
        self.context = context
        self.config: Optional[WinRemoteConfig] = None
        self.auth_manager: Optional[AuthManager] = None
        self.server: Optional[WinRemoteServer] = None
        self.tool_handlers: Optional[ToolHandlers] = None
        self._initialized = False
    
    def initialize(self):
        """初始化插件"""
        if self._initialized:
            logger.warning("插件已初始化")
            return
        
        # 加载配置
        self.config = WinRemoteConfig.load(DEFAULT_CONFIG_PATH)
        is_valid, error = self.config.validate()
        if not is_valid:
            logger.error(f"配置验证失败：{error}")
            raise ValueError(f"配置错误：{error}")
        
        # 初始化认证
        self.auth_manager = AuthManager(
            auth_token=self.config.auth_token,
            session_timeout_minutes=self.config.session_timeout_minutes
        )
        
        # 初始化服务器
        self.server = WinRemoteServer(port=self.config.server_port)
        self.server.set_auth_manager(self.auth_manager)
        
        # 初始化工具处理器
        self.tool_handlers = ToolHandlers()
        self.tool_handlers.register_all(self.server)
        
        # 启动服务器
        self.server.start()
        
        self._initialized = True
        logger.info("WinRemote 插件初始化完成")
    
    def destroy(self):
        """销毁插件"""
        if self.server:
            self.server.stop()
        self._initialized = False
        logger.info("WinRemote 插件已销毁")
    
    async def handle_message(self, event: MessageEvent) -> Optional[MessageChain]:
        """处理消息（可选的聊天命令入口）"""
        message = event.get_message()
        if not message:
            return None
        
        text = message.strip()
        
        # 简单的命令处理
        if text.startswith("/winremote "):
            cmd = text[11:].strip()
            if cmd == "status":
                return MessageChain().text("WinRemote 服务器运行中喵～")
            elif cmd == "restart":
                self.destroy()
                self.initialize()
                return MessageChain().text("WinRemote 已重启喵～")
        
        return None
    
    def get_tools(self) -> list:
        """获取工具列表（用于 Function Calling）"""
        return get_tools_schema()
    
    async def call_tool(self, name: str, args: dict) -> dict:
        """调用工具（Function Calling 入口）"""
        if not self._initialized:
            return {"success": False, "error": "插件未初始化"}
        
        # 这里可以调用实际的 Agent 客户端
        # 现在返回占位结果
        return {
            "success": True,
            "data": {"message": f"工具 {name} 调用成功", "args": args}
        }
