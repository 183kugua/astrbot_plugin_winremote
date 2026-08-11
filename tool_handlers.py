"""WinRemote 工具处理器（支持 image 返回）"""
import logging
from typing import Dict, Any, Optional
from .models import CommandResult

logger = logging.getLogger(__name__)


class ToolHandlers:
    """工具处理器集合"""
    
    def __init__(self, agent_client=None):
        self.agent_client = agent_client
    
    def register_all(self, server):
        """注册所有工具处理器到服务器"""
        tools = {
            '/api/agent/status': self.agent_status,
            '/api/tool/win_shell': self.win_shell,
            '/api/tool/win_powershell': self.win_powershell,
            '/api/tool/win_screenshot': self.win_screenshot,
            '/api/tool/win_keypress': self.win_keypress,
            '/api/tool/win_mouse': self.win_mouse,
            '/api/tool/win_open': self.win_open,
            '/api/tool/win_type': self.win_type,
        }
        
        for path, handler in tools.items():
            server.register_route(path, 'POST', handler)
        
        logger.info(f"注册了 {len(tools)} 个工具处理器")
    
    def _build_response(self, success: bool, data: dict = None, error: str = None, 
                        image_data: bytes = None, image_format: str = "PNG") -> dict:
        """构建响应"""
        response = {
            "success": success,
            "data": data or {}
        }
        if error:
            response["error"] = error
        if image_data:
            import base64
            response["image_data"] = base64.b64encode(image_data).decode('utf-8')
            response["image_format"] = image_format
        return response
    
    async def _call_agent(self, tool_name: str, params: dict) -> CommandResult:
        """调用 Agent 工具"""
        if not self.agent_client:
            raise RuntimeError("Agent 客户端未初始化")
        
        # 这里会由实际的 Agent 客户端实现
        # 现在返回占位结果
        return CommandResult(
            success=True,
            output=f"[模拟] {tool_name} 执行成功",
            execution_time_ms=100
        )
    
    def agent_status(self, data: dict) -> dict:
        """获取 Agent 状态"""
        try:
            # 实际实现会调用 agent_client
            return self._build_response(True, {
                "status": "online",
                "agents": []
            })
        except Exception as e:
            logger.exception("agent_status 错误")
            return self._build_response(False, error=str(e))
    
    def win_shell(self, data: dict) -> dict:
        """执行 CMD 命令"""
        try:
            command = data.get('command', '')
            if not command:
                return self._build_response(False, error="command 参数不能为空")
            
            # 调用 Agent
            result = self.agent_client.execute_shell(command) if self.agent_client else None
            
            return self._build_response(True, {
                "output": result.output if result else f"[模拟] 执行命令：{command}",
                "execution_time_ms": result.execution_time_ms if result else 0
            })
        except Exception as e:
            logger.exception("win_shell 错误")
            return self._build_response(False, error=str(e))
    
    def win_powershell(self, data: dict) -> dict:
        """执行 PowerShell 命令"""
        try:
            command = data.get('command', '')
            if not command:
                return self._build_response(False, error="command 参数不能为空")
            
            return self._build_response(True, {
                "output": f"[模拟] 执行 PowerShell：{command}",
                "execution_time_ms": 100
            })
        except Exception as e:
            logger.exception("win_powershell 错误")
            return self._build_response(False, error=str(e))
    
    def win_screenshot(self, data: dict) -> dict:
        """截取屏幕截图（返回图片）"""
        try:
            format = data.get('format', 'PNG')
            quality = data.get('quality', 75)
            
            # 实际实现会获取截图数据
            # 这里返回占位
            return self._build_response(True, {
                "message": f"截图成功 (格式：{format}, 质量：{quality})"
            })
        except Exception as e:
            logger.exception("win_screenshot 错误")
            return self._build_response(False, error=str(e))
    
    def win_keypress(self, data: dict) -> dict:
        """模拟键盘按键"""
        try:
            keys = data.get('keys', '')
            if not keys:
                return self._build_response(False, error="keys 参数不能为空")
            
            return self._build_response(True, {
                "message": f"模拟按键：{keys}"
            })
        except Exception as e:
            logger.exception("win_keypress 错误")
            return self._build_response(False, error=str(e))
    
    def win_mouse(self, data: dict) -> dict:
        """模拟鼠标操作"""
        try:
            button = data.get('button', 'click')
            x = data.get('x', 0)
            y = data.get('y', 0)
            
            return self._build_response(True, {
                "message": f"模拟鼠标：{button} at ({x}, {y})"
            })
        except Exception as e:
            logger.exception("win_mouse 错误")
            return self._build_response(False, error=str(e))
    
    def win_open(self, data: dict) -> dict:
        """打开程序/文件/URL"""
        try:
            target = data.get('target', '')
            if not target:
                return self._build_response(False, error="target 参数不能为空")
            
            return self._build_response(True, {
                "message": f"打开：{target}"
            })
        except Exception as e:
            logger.exception("win_open 错误")
            return self._build_response(False, error=str(e))
    
    def win_type(self, data: dict) -> dict:
        """模拟键盘输入文本"""
        try:
            text = data.get('text', '')
            if not text:
                return self._build_response(False, error="text 参数不能为空")
            
            return self._build_response(True, {
                "message": f"输入文本：{text}"
            })
        except Exception as e:
            logger.exception("win_type 错误")
            return self._build_response(False, error=str(e))
