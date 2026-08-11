"""WinRemote 安全校验模块"""
import re
from typing import List, Tuple
try:
    from .models import SecurityPolicy
except ImportError:
    from models import SecurityPolicy


class SecurityValidator:
    """命令和路径安全校验器"""
    
    DANGEROUS_PATTERNS = [
        r'\|',           # 管道
        r'&',            # 逻辑与
        r';',            # 命令分隔
        r'`',            # 反引号
        r'\$',           # 变量
        r'\(',           # 子命令
        r'\)',           # 子命令
        r'>',            # 重定向
        r'<',            # 重定向
        r'%',            # 变量
        r'!',            # 历史命令
    ]
    
    SENSITIVE_COMMANDS = [
        "del", "erase", "rd", "rmdir", "format", "diskpart",
        "reg", "net user", "net localgroup", "shutdown", "taskkill",
        "cacls", "icacls", "takeown", "attrib"
    ]
    
    SENSITIVE_PATHS = [
        "C:/Windows/System32",
        "C:/Program Files",
        "C:/Program Files (x86)",
        "C:/Users/*/AppData",
        "/etc/", "/bin/", "/usr/", "/root/"
    ]
    
    def __init__(self, policy: SecurityPolicy = None):
        self.policy = policy or SecurityPolicy()
    
    def validate_command(self, cmd: str, allowed_commands: List[str] = None) -> Tuple[bool, str]:
        """
        验证命令是否安全
        返回：(是否安全，错误消息)
        """
        if not cmd or len(cmd.strip()) == 0:
            return False, "命令不能为空"
        
        if len(cmd) > self.policy.max_command_length:
            return False, f"命令长度超过限制 ({self.policy.max_command_length} 字符)"
        
        # 检查危险字符
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd):
                return False, f"命令包含危险字符：{pattern}"
        
        # 检查敏感命令
        cmd_lower = cmd.lower()
        for sensitive in self.SENSITIVE_COMMANDS:
            if sensitive in cmd_lower:
                return False, f"命令包含敏感操作：{sensitive}"
        
        # 检查白名单（如果提供了）
        if allowed_commands:
            cmd_base = cmd.split()[0].lower() if cmd.split() else ""
            if cmd_base and cmd_base not in [c.lower() for c in allowed_commands]:
                return False, f"命令不在白名单中：{cmd_base}"
        
        return True, ""
    
    def validate_path(self, path: str, allowed_paths: List[str] = None) -> Tuple[bool, str]:
        """
        验证路径是否安全
        返回：(是否安全，错误消息)
        """
        if not path:
            return False, "路径不能为空"
        
        path_normalized = path.replace("\\", "/")
        
        # 检查敏感路径
        for sensitive in self.SENSITIVE_PATHS:
            sensitive_norm = sensitive.replace("\\", "/")
            if sensitive_norm in path_normalized:
                return False, f"路径在敏感范围内：{sensitive}"
        
        # 检查白名单（如果提供了）
        if allowed_paths:
            for allowed in allowed_paths:
                allowed_norm = allowed.replace("\\", "/")
                if path_normalized.startswith(allowed_norm):
                    return True, ""
            return False, "路径不在允许的范围内"
        
        return True, ""
    
    def sanitize_command(self, cmd: str) -> str:
        """清理命令中的危险字符"""
        # 移除危险字符
        for pattern in self.DANGEROUS_PATTERNS:
            cmd = re.sub(pattern, '', cmd)
        return cmd.strip()
    
    def is_auth_required(self, cmd: str) -> bool:
        """检查是否需要额外认证"""
        if not self.policy.require_auth_for_sensitive:
            return False
        
        cmd_lower = cmd.lower()
        for sensitive in self.SENSITIVE_COMMANDS:
            if sensitive in cmd_lower:
                return True
        return False
