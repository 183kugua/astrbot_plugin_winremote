"""WinRemote 插件测试 - 独立模块测试"""
import pytest
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 只导入不依赖 astrbot API 的模块
from config import WinRemoteConfig
from security import SecurityValidator
from auth import AuthManager
from models import SecurityPolicy, AgentConnection
from datetime import datetime, timedelta


class TestWinRemoteConfig:
    """配置测试"""
    
    def test_default_config(self):
        config = WinRemoteConfig()
        assert config.server_port == 8765
        assert config.auth_token == ""
        assert config.block_sensitive == True
    
    def test_validate_empty_token(self):
        config = WinRemoteConfig(auth_token="")
        is_valid, error = config.validate()
        assert is_valid == False
        assert "auth_token" in error
    
    def test_validate_short_token(self):
        config = WinRemoteConfig(auth_token="1234567")
        is_valid, error = config.validate()
        assert is_valid == False
    
    def test_validate_valid_config(self):
        config = WinRemoteConfig(auth_token="valid_token_123")
        is_valid, error = config.validate()
        assert is_valid == True
        assert error == ""
    
    def test_validate_invalid_port(self):
        config = WinRemoteConfig(server_port=80)
        is_valid, error = config.validate()
        assert is_valid == False


class TestSecurityValidator:
    """安全校验测试"""
    
    def setup_method(self):
        self.validator = SecurityValidator()
    
    def test_empty_command(self):
        is_allowed, error = self.validator.validate_command("")
        assert is_allowed == False
    
    def test_dangerous_characters(self):
        is_allowed, error = self.validator.validate_command("cmd | dir")
        assert is_allowed == False
        assert "危险字符" in error
    
    def test_sensitive_command(self):
        is_allowed, error = self.validator.validate_command("del C:\\file.txt")
        assert is_allowed == False
        assert "敏感操作" in error
    
    def test_safe_command(self):
        is_allowed, error = self.validator.validate_command("ipconfig /all")
        assert is_allowed == True
    
    def test_command_too_long(self):
        long_cmd = "a" * 600
        is_allowed, error = self.validator.validate_command(long_cmd)
        assert is_allowed == False
    
    def test_sensitive_path(self):
        is_allowed, error = self.validator.validate_path("C:/Windows/System32/calc.exe")
        assert is_allowed == False
    
    def test_safe_path(self):
        is_allowed, error = self.validator.validate_path("D:/Documents/file.txt")
        assert is_allowed == True


class TestAuthManager:
    """认证管理测试"""
    
    def setup_method(self):
        self.auth = AuthManager(auth_token="test_token_12345", session_timeout_minutes=30)
    
    def test_valid_token(self):
        is_valid, error = self.auth.validate_token("test_token_12345")
        assert is_valid == True
    
    def test_empty_token(self):
        is_valid, error = self.auth.validate_token("")
        assert is_valid == False
    
    def test_invalid_token(self):
        is_valid, error = self.auth.validate_token("wrong_token")
        assert is_valid == False
    
    def test_create_session_token(self):
        session_token = self.auth.create_session_token()
        assert len(session_token) > 0
        
        is_valid, error = self.auth.validate_token(session_token)
        assert is_valid == True
    
    def test_revoke_token(self):
        session_token = self.auth.create_session_token()
        result = self.auth.revoke_token(session_token)
        assert result == True
        
        is_valid, error = self.auth.validate_token(session_token)
        assert is_valid == False


class TestModels:
    """数据模型测试"""
    
    def test_agent_connection_to_dict(self):
        conn = AgentConnection(
            agent_id="test-001",
            agent_name="TestAgent",
            ip_address="192.168.1.100",
            port=8765,
            status="online",
            last_heartbeat=datetime.now(),
            os_info="Windows 11",
            username="admin"
        )
        
        data = conn.to_dict()
        assert data["agent_id"] == "test-001"
        assert data["status"] == "online"
    
    def test_agent_connection_from_dict(self):
        data = {
            "agent_id": "test-001",
            "agent_name": "TestAgent",
            "ip_address": "192.168.1.100",
            "port": 8765,
            "status": "online",
            "last_heartbeat": datetime.now().isoformat(),
            "os_info": "Windows 11",
            "username": "admin"
        }
        
        conn = AgentConnection.from_dict(data)
        assert conn.agent_id == "test-001"
        assert conn.status == "online"
    
    def test_security_policy_block_command(self):
        policy = SecurityPolicy()
        is_allowed, error = policy.is_command_allowed("del file.txt")
        assert is_allowed == False
    
    def test_security_policy_allow_command(self):
        policy = SecurityPolicy()
        is_allowed, error = policy.is_command_allowed("dir")
        assert is_allowed == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
