"""WinRemote 类型化配置模块"""
from dataclasses import dataclass, field
from typing import List, Optional
import json
import os


@dataclass
class WinRemoteConfig:
    """WinRemote 插件配置"""
    server_port: int = 8765
    auth_token: str = ""
    allowed_commands: List[str] = field(default_factory=lambda: [
        "ipconfig", "tasklist", "dir", "systeminfo", "ping", "netstat"
    ])
    allowed_paths: List[str] = field(default_factory=lambda: [
        "C:/Users", "D:/", "E:/"
    ])
    block_sensitive: bool = True
    max_output_length: int = 5000
    screenshot_quality: int = 75
    session_timeout_minutes: int = 30
    
    def validate(self) -> tuple[bool, str]:
        """验证配置合法性"""
        if not self.auth_token or len(self.auth_token) < 8:
            return False, "auth_token 长度至少 8 位"
        if not (1024 <= self.server_port <= 65535):
            return False, "端口必须在 1024-65535 范围"
        if not self.allowed_commands:
            return False, "allowed_commands 不能为空"
        return True, ""
    
    @classmethod
    def load(cls, config_path: str) -> "WinRemoteConfig":
        """从 JSON 文件加载配置"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls(**data)
        return cls()
    
    def save(self, config_path: str) -> None:
        """保存配置到 JSON 文件"""
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump({
                "server_port": self.server_port,
                "auth_token": self.auth_token,
                "allowed_commands": self.allowed_commands,
                "allowed_paths": self.allowed_paths,
                "block_sensitive": self.block_sensitive,
                "max_output_length": self.max_output_length,
                "screenshot_quality": self.screenshot_quality,
                "session_timeout_minutes": self.session_timeout_minutes
            }, f, indent=2, ensure_ascii=False)


# 配置路径常量
DEFAULT_CONFIG_PATH = "data/plugins/astrbot_plugin_winremote/config.json"
