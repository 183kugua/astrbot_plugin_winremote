"""WinRemote 认证管理模块"""
import hashlib
import time
from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class TokenInfo:
    """Token 信息"""
    token_hash: str
    created_at: datetime
    expires_at: datetime
    is_valid: bool = True


class AuthManager:
    """认证管理器（去除 audit 死代码）"""
    
    def __init__(self, auth_token: str, session_timeout_minutes: int = 30):
        self.auth_token_hash = self._hash_token(auth_token)
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        self.active_tokens: Dict[str, TokenInfo] = {}
    
    def _hash_token(self, token: str) -> str:
        """对 Token 进行 SHA256 哈希"""
        return hashlib.sha256(token.encode('utf-8')).hexdigest()
    
    def validate_token(self, token: str) -> tuple[bool, str]:
        """
        验证 Token 是否有效
        返回：(是否有效，错误消息)
        """
        if not token:
            return False, "Token 不能为空"
        
        token_hash = self._hash_token(token)
        
        # 检查是否是主 Token
        if token_hash == self.auth_token_hash:
            return True, ""
        
        # 检查是否是活动 Token
        if token_hash in self.active_tokens:
            token_info = self.active_tokens[token_hash]
            if not token_info.is_valid:
                return False, "Token 已被撤销"
            if datetime.now() > token_info.expires_at:
                # Token 过期，清理
                del self.active_tokens[token_hash]
                return False, "Token 已过期"
            return True, ""
        
        return False, "Token 无效"
    
    def create_session_token(self) -> str:
        """创建会话 Token"""
        import uuid
        new_token = str(uuid.uuid4())
        token_hash = self._hash_token(new_token)
        
        now = datetime.now()
        self.active_tokens[token_hash] = TokenInfo(
            token_hash=token_hash,
            created_at=now,
            expires_at=now + self.session_timeout
        )
        
        return new_token
    
    def revoke_token(self, token: str) -> bool:
        """撤销 Token"""
        token_hash = self._hash_token(token)
        if token_hash in self.active_tokens:
            self.active_tokens[token_hash].is_valid = False
            return True
        return False
    
    def cleanup_expired(self) -> int:
        """清理过期 Token，返回清理数量"""
        now = datetime.now()
        expired = [k for k, v in self.active_tokens.items() if now > v.expires_at]
        for k in expired:
            del self.active_tokens[k]
        return len(expired)
    
    def get_token_info(self, token: str) -> Optional[TokenInfo]:
        """获取 Token 信息"""
        token_hash = self._hash_token(token)
        return self.active_tokens.get(token_hash)
