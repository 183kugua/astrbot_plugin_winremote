"""WinRemote Agent 测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.winremote_agent import WinRemoteAgent


class TestWinRemoteAgent:
    """Agent 测试"""
    
    def setup_method(self):
        self.agent = WinRemoteAgent(config_path="agent/agent_config.example.json")
    
    def test_agent_id_generated(self):
        assert len(self.agent.agent_id) > 0
    
    def test_get_status(self):
        status = self.agent.get_status()
        assert "agent_id" in status
        assert "hostname" in status
        assert status["agent_id"] == self.agent.agent_id
    
    def test_execute_shell_basic(self):
        """测试基本 CMD 命令（需要 Windows 环境）"""
        result = self.agent.execute_shell("echo Hello")
        assert "success" in result
    
    def test_execute_powershell_basic(self):
        """测试基本 PowerShell 命令（需要 Windows 环境）"""
        result = self.agent.execute_powershell("Get-Date")
        assert "success" in result
    
    def test_take_screenshot(self):
        """测试截图（需要 Windows 环境）"""
        result = self.agent.take_screenshot(format="PNG")
        assert "success" in result
    
    def test_send_keypress(self):
        """测试按键（需要 Windows 环境）"""
        result = self.agent.send_keypress("ctrl")
        assert "success" in result
    
    def test_send_mouse(self):
        """测试鼠标（需要 Windows 环境）"""
        result = self.agent.send_mouse(button="move", x=100, y=100)
        assert "success" in result
    
    def test_type_text(self):
        """测试文本输入（需要 Windows 环境）"""
        result = self.agent.type_text("Hello World")
        assert "success" in result
    
    def test_open_target(self):
        """测试打开目标（需要 Windows 环境）"""
        result = self.agent.open_target("notepad")
        assert "success" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
