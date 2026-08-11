"""WinRemote 数据模型定义"""
from dataclasses import dataclass, field
from typing import Optional, Any, List
from datetime import datetime
import uuid


@dataclass
class AgentConnection:
    """Agent 连接信息"""
    agent_id: str
    agent_name: str
    ip_address: str
    port: int
    status: str  # online/offline/busy/idle
    last_heartbeat: datetime
    os_info: str = ""
    username: str = ""
    
    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "ip_address": self.ip_address,
            "port": self.port,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "os_info": self.os_info,
            "username": self.username
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentConnection":
        return cls(
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            ip_address=data["ip_address"],
            port=data["port"],
            status=data["status"],
            last_heartbeat=datetime.fromisoformat(data["last_heartbeat"]),
            os_info=data.get("os_info", ""),
            username=data.get("username", "")
        )


@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool
    output: str
    error: str = ""
    execution_time_ms: int = 0
    screenshot_path: Optional[str] = None
    image_data: Optional[bytes] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms
        }


@dataclass
class RemoteSession:
    """远程会话管理"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    shell_sessions: List[str] = field(default_factory=list)
    
    def is_expired(self, timeout_minutes: int) -> bool:
        elapsed = (datetime.now() - self.last_activity).total_seconds() / 60
        return elapsed > timeout_minutes
    
    def touch(self) -> None:
        self.last_activity = datetime.now()


@dataclass
class SecurityPolicy:
    """安全策略"""
    block_paths: List[str] = field(default_factory=lambda: [
        "C:/Windows/System32",
        "C:/Program Files",
        "C:/Program Files (x86)"
    ])
    block_commands: List[str] = field(default_factory=lambda: [
        "del", "rd", "format", "diskpart", "reg",
        "net user", "net localgroup", "shutdown", "taskkill"
    ])
    max_command_length: int = 500
    require_auth_for_sensitive: bool = True
    
    def is_command_allowed(self, cmd: str) -> tuple[bool, str]:
        """检查命令是否允许"""
        cmd_lower = cmd.lower()
        for blocked in self.block_commands:
            if blocked.lower() in cmd_lower:
                return False, f"命令包含被阻止的关键字：{blocked}"
        return True, ""
    
    def is_path_allowed(self, path: str) -> tuple[bool, str]:
        """检查路径是否允许访问"""
        path_normalized = path.replace("\\", "/")
        for blocked in self.block_paths:
            if path_normalized.startswith(blocked.replace("\\", "/")):
                return False, f"路径在被阻止的范围内：{blocked}"
        return True, ""
