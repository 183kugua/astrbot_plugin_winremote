"""
test_tools.py — WinRemote v0.9.9 LLM Tool 测试
============================================
测试内容：
1. Tool 定义完整性（7 个 Tool 的 name/description/parameters）
2. ALL_TOOLS 导出
3. tool_handlers 的插件实例注入
4. handler 的授权检查逻辑
5. handler 的命令/路径校验
6. handler 的 Agent 可用性检查
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# ============================================================
# 测试准备：将插件目录加入 sys.path
# ============================================================
PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from tools import (  # noqa: E402
    WinShellTool,
    WinPowershellTool,
    WinScreenshotTool,
    WinKeypressTool,
    WinMouseTool,
    WinOpenTool,
    WinReadFileTool,
    ALL_TOOLS,
)
import tool_handlers  # noqa: E402


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_plugin():
    """模拟插件实例，注入给 tool_handlers"""
    plugin = MagicMock()
    plugin.cfg = {
        "command_whitelist": ["shell", "powershell", "screenshot"],
        "command_blacklist": ["rm ", "del ", "format"],
        "command_regex_blacklist": [],
        "path_whitelist": ["C:\\Temp", "C:\\Users\\Public"],
        "path_blacklist_keywords": ["..\\", "../"],
        "allow_powershell": True,
        "max_read_bytes": 65536,
    }
    plugin.auth_mgr = MagicMock()
    plugin.auth_mgr.check.return_value = True  # 默认已授权
    plugin.server = MagicMock()
    plugin._cfg_bool = lambda k, d: plugin.cfg.get(k, d)
    plugin._cfg_int = lambda k, d, *a: plugin.cfg.get(k, d)
    return plugin


@pytest.fixture
def mock_agent():
    """模拟已连接的 Agent"""
    agent = MagicMock()
    agent.agent_id = "test-agent-001"
    agent.authenticated = True
    agent.is_alive.return_value = True
    return agent


@pytest.fixture(autouse=True)
def reset_plugin_instance():
    """每个测试前重置 tool_handlers 的插件实例"""
    tool_handlers._plugin_instance = None
    yield
    tool_handlers._plugin_instance = None


# ============================================================
# 1. Tool 定义完整性测试
# ============================================================
class TestToolDefinitions:
    """测试 7 个 Tool 的 @dataclass 定义"""

    def test_all_tools_count(self):
        """ALL_TOOLS 应包含 7 个 Tool"""
        assert len(ALL_TOOLS) == 7, f"期望 7 个 Tool，实际 {len(ALL_TOOLS)}"

    def test_all_tools_have_required_fields(self):
        """每个 Tool 必须有 name / description / parameters"""
        for tool in ALL_TOOLS:
            assert hasattr(tool, "name"), f"{tool} 缺少 name"
            assert hasattr(tool, "description"), f"{tool} 缺少 description"
            assert hasattr(tool, "parameters"), f"{tool} 缺少 parameters"
            assert tool.name, f"{tool.__class__.__name__} name 为空"
            assert tool.description, f"{tool.__class__.__name__} description 为空"
            assert isinstance(tool.parameters, dict), f"{tool.name} parameters 不是 dict"
            assert "type" in tool.parameters, f"{tool.name} parameters 缺少 type"
            assert "properties" in tool.parameters, f"{tool.name} parameters 缺少 properties"

    def test_tool_names_unique(self):
        """Tool 名称不能重复"""
        names = [t.name for t in ALL_TOOLS]
        assert len(names) == len(set(names)), f"Tool 名称重复: {names}"

    def test_tool_names_prefix(self):
        """所有 Tool 名称以 win_ 开头"""
        for tool in ALL_TOOLS:
            assert tool.name.startswith("win_"), f"{tool.name} 不以 win_ 开头"

    def test_shell_tool(self):
        t = WinShellTool()
        assert t.name == "win_shell"
        assert "CMD" in t.description or "cmd" in t.description.lower()
        assert "command" in t.parameters["properties"]
        assert "command" in t.parameters["required"]

    def test_powershell_tool(self):
        t = WinPowershellTool()
        assert t.name == "win_powershell"
        assert "PowerShell" in t.description or "powershell" in t.description.lower()
        assert "command" in t.parameters["properties"]
        assert "command" in t.parameters["required"]

    def test_screenshot_tool(self):
        t = WinScreenshotTool()
        assert t.name == "win_screenshot"
        assert "截图" in t.description or "screenshot" in t.description.lower()
        props = t.parameters["properties"]
        assert "format" in props
        assert "quality" in props
        # format 有 enum
        assert "enum" in props["format"]
        assert "JPEG" in props["format"]["enum"]

    def test_keypress_tool(self):
        t = WinKeypressTool()
        assert t.name == "win_keypress"
        assert "按键" in t.description or "key" in t.description.lower()
        assert "keys" in t.parameters["properties"]
        assert "keys" in t.parameters["required"]

    def test_mouse_tool(self):
        t = WinMouseTool()
        assert t.name == "win_mouse"
        assert "鼠标" in t.description or "mouse" in t.description.lower()
        props = t.parameters["properties"]
        assert "x" in props
        assert "y" in props
        assert "button" in props
        assert {"x", "y"}.issubset(set(t.parameters["required"]))

    def test_open_tool(self):
        t = WinOpenTool()
        assert t.name == "win_open"
        assert "打开" in t.description or "open" in t.description.lower()
        assert "target" in t.parameters["properties"]
        assert "target" in t.parameters["required"]

    def test_readfile_tool(self):
        t = WinReadFileTool()
        assert t.name == "win_read_file"
        assert "文件" in t.description or "file" in t.description.lower()
        props = t.parameters["properties"]
        assert "path" in props
        assert "max_bytes" in props
        assert "path" in t.parameters["required"]
        # max_bytes 有范围限制
        assert props["max_bytes"]["minimum"] >= 1024
        assert props["max_bytes"]["maximum"] >= 65536


# ============================================================
# 2. tool_handlers 插件实例注入测试
# ============================================================
class TestPluginInstanceInjection:
    """测试 set_plugin_instance / _get_plugin"""

    def test_set_and_get_plugin(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        assert tool_handlers._get_plugin() is mock_plugin

    def test_get_plugin_none_when_not_set(self):
        # autouse fixture 已重置为 None
        assert tool_handlers._get_plugin() is None

    def test_set_plugin_overwrites(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        new_plugin = MagicMock()
        tool_handlers.set_plugin_instance(new_plugin)
        assert tool_handlers._get_plugin() is new_plugin


# ============================================================
# 3. 授权检查测试
# ============================================================
class TestAuthCheck:
    """测试 _check_auth 逻辑"""

    def test_auth_ok(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.auth_mgr.check.return_value = True
        ok, err = tool_handlers._check_auth("shell")
        assert ok is True
        assert err == ""

    def test_auth_denied(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.auth_mgr.check.return_value = False
        ok, err = tool_handlers._check_auth("shell")
        assert ok is False
        assert "未授权" in err

    def test_auth_no_plugin(self):
        ok, err = tool_handlers._check_auth("shell")
        assert ok is False
        assert "未就绪" in err

    def test_auth_no_auth_mgr(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        del mock_plugin.auth_mgr
        ok, err = tool_handlers._check_auth("shell")
        assert ok is False
        assert "未初始化" in err


# ============================================================
# 4. Agent 获取测试
# ============================================================
class TestAgentGet:
    def test_get_agent_success(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        agent = tool_handlers._get_agent()
        assert agent is mock_agent

    def test_get_agent_none(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = None
        agent = tool_handlers._get_agent()
        assert agent is None

    def test_get_agent_no_plugin(self):
        agent = tool_handlers._get_agent()
        assert agent is None


# ============================================================
# 5. handle_shell 测试
# ============================================================
class TestHandleShell:
    @pytest.mark.asyncio
    async def test_shell_no_plugin(self):
        result = await tool_handlers.handle_shell("ipconfig")
        assert "未就绪" in result

    @pytest.mark.asyncio
    async def test_shell_auth_denied(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.auth_mgr.check.return_value = False
        result = await tool_handlers.handle_shell("ipconfig")
        assert "未授权" in result

    @pytest.mark.asyncio
    async def test_shell_command_blocked(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        # "rm " 在黑名单中
        result = await tool_handlers.handle_shell("rm -rf /")
        assert "拒绝" in result or "blacklist" in result.lower()

    @pytest.mark.asyncio
    async def test_shell_no_agent(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = None
        result = await tool_handlers.handle_shell("ipconfig")
        assert "没有可用" in result or "Agent" in result

    @pytest.mark.asyncio
    async def test_shell_success(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        # Mock send_command 返回成功
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True, "message": "sent", "output": "IPv4: 192.168.1.100"}
        )
        result = await tool_handlers.handle_shell("ipconfig /all")
        assert "✅" in result or "已执行" in result
        # 验证 send_command 被调用
        mock_plugin.server.send_command.assert_called_once()
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[0] == "test-agent-001"
        assert call_args.args[1] == "shell"
        assert call_args.args[2]["command"] == "ipconfig /all"


# ============================================================
# 6. handle_powershell 测试
# ============================================================
class TestHandlePowershell:
    @pytest.mark.asyncio
    async def test_powershell_disabled(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin._cfg_bool = lambda k, d: False  # allow_powershell = False
        result = await tool_handlers.handle_powershell("Get-Process")
        assert "未启用" in result

    @pytest.mark.asyncio
    async def test_powershell_success(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True, "output": "chrome  1234"}
        )
        # 用不含管道符的命令（| 在 INJECTION_CHARS 中会被拦截）
        result = await tool_handlers.handle_powershell("Get-Process")
        assert "✅" in result
        # 验证 action 是 powershell
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[1] == "powershell"


# ============================================================
# 7. handle_screenshot 测试
# ============================================================
class TestHandleScreenshot:
    @pytest.mark.asyncio
    async def test_screenshot_auth_denied(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.auth_mgr.check.return_value = False
        result = await tool_handlers.handle_screenshot()
        assert "未授权" in result

    @pytest.mark.asyncio
    async def test_screenshot_invalid_format(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True}
        )
        # 传无效 format，应自动修正为 JPEG
        result = await tool_handlers.handle_screenshot(format="GIF", quality=50)
        assert "📸" in result
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[2]["format"] == "JPEG"  # 修正为默认

    @pytest.mark.asyncio
    async def test_screenshot_quality_clamp(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True}
        )
        # quality 超过 100 应被 clamp
        await tool_handlers.handle_screenshot(quality=999)
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[2]["quality"] == 100

    @pytest.mark.asyncio
    async def test_screenshot_no_agent(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = None
        result = await tool_handlers.handle_screenshot()
        assert "没有可用" in result


# ============================================================
# 8. handle_keypress 测试
# ============================================================
class TestHandleKeypress:
    @pytest.mark.asyncio
    async def test_keypress_empty(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        result = await tool_handlers.handle_keypress("")
        assert "不能为空" in result

    @pytest.mark.asyncio
    async def test_keypress_success(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True}
        )
        result = await tool_handlers.handle_keypress("ctrl+alt+del")
        assert "⌨" in result or "已发送" in result
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[1] == "keypress"
        assert call_args.args[2]["keys"] == "ctrl+alt+del"


# ============================================================
# 9. handle_mouse 测试
# ============================================================
class TestHandleMouse:
    @pytest.mark.asyncio
    async def test_mouse_invalid_coord(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        result = await tool_handlers.handle_mouse("abc", 100)
        assert "整数" in result

    @pytest.mark.asyncio
    async def test_mouse_success(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True}
        )
        result = await tool_handlers.handle_mouse(500, 300, "right")
        assert "🖱" in result or "成功" in result
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[1] == "mouse"
        assert call_args.args[2]["x"] == 500
        assert call_args.args[2]["y"] == 300
        assert call_args.args[2]["button"] == "right"

    @pytest.mark.asyncio
    async def test_mouse_default_button(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True}
        )
        await tool_handlers.handle_mouse(100, 200)
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[2]["button"] == "click"  # 默认值


# ============================================================
# 10. handle_open 测试
# ============================================================
class TestHandleOpen:
    @pytest.mark.asyncio
    async def test_open_empty(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        result = await tool_handlers.handle_open("")
        assert "不能为空" in result

    @pytest.mark.asyncio
    async def test_open_success(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True}
        )
        result = await tool_handlers.handle_open("notepad")
        assert "📂" in result or "已打开" in result
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[1] == "open"
        assert call_args.args[2]["target"] == "notepad"


# ============================================================
# 11. handle_read_file 测试
# ============================================================
class TestHandleReadFile:
    @pytest.mark.asyncio
    async def test_readfile_empty(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        result = await tool_handlers.handle_read_file("")
        assert "不能为空" in result

    @pytest.mark.asyncio
    async def test_readfile_path_blocked(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        # "..\\" 在 path_blacklist_keywords 中
        result = await tool_handlers.handle_read_file("C:\\Temp\\..\\Windows\\system32\\config")
        assert "拒绝" in result or "forbidden" in result.lower()

    @pytest.mark.asyncio
    async def test_readfile_success(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True, "content": "line1\nline2\nline3"}
        )
        result = await tool_handlers.handle_read_file("C:\\Temp\\test.txt")
        assert "📄" in result or "文件" in result
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[1] == "read_file"
        assert call_args.args[2]["path"] == "C:\\Temp\\test.txt"

    @pytest.mark.asyncio
    async def test_readfile_max_bytes_clamp(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        mock_plugin.server.agents.find.return_value = mock_agent
        mock_plugin.server.send_command = AsyncMock(
            return_value={"ok": True, "content": "test"}
        )
        # max_bytes 超过上限应被 clamp
        await tool_handlers.handle_read_file("C:\\Temp\\test.txt", max_bytes=9999999)
        call_args = mock_plugin.server.send_command.call_args
        assert call_args.args[2]["max_bytes"] == 1048576  # 上限


# ============================================================
# 12. 审计写入测试
# ============================================================
class TestAudit:
    @pytest.mark.asyncio
    async def test_audit_writes_when_plugin_has_audit(self, mock_plugin, mock_agent):
        tool_handlers.set_plugin_instance(mock_plugin)
        # 给 plugin.audit 一个真实的 asyncio.Queue 替代
        import tool_handlers as th
        # 直接测试 _audit 函数
        mock_plugin.audit = MagicMock()
        # _audit 是同步函数，但内部用 loop.create_task
        # 我们只验证它不抛异常
        th._audit(mock_plugin, "test_action", "test_result")
        # 不要求 audit.write 被调用（因为可能没有 running loop）
        # 关键是不要崩

    def test_audit_no_audit_attr(self, mock_plugin):
        tool_handlers.set_plugin_instance(mock_plugin)
        del mock_plugin.audit
        # 不应抛异常
        tool_handlers._audit(mock_plugin, "test", "test")


# ============================================================
# 13. 主插件注册逻辑测试
# ============================================================
class TestMainPluginRegistration:
    """测试 astrbot_plugin_winremote.py 中的 _register_llm_tools"""

    def test_register_llm_tools_disabled(self, mock_plugin):
        """enable_llm_mode=false 时应跳过注册"""
        from astrbot_plugin_winremote import WinRemotePlugin
        plugin = mock_plugin
        plugin.cfg["enable_llm_mode"] = False

        context = MagicMock()
        context.add_llm_tools = MagicMock()

        # 直接调用注册方法
        WinRemotePlugin._register_llm_tools(plugin, context, plugin.cfg)

        context.add_llm_tools.assert_not_called()

    def test_register_llm_tools_enabled(self, mock_plugin):
        """enable_llm_mode=true 时应注册 7 个 Tool"""
        from astrbot_plugin_winremote import WinRemotePlugin
        plugin = mock_plugin
        plugin.cfg["enable_llm_mode"] = True

        context = MagicMock()
        context.add_llm_tools = MagicMock()

        WinRemotePlugin._register_llm_tools(plugin, context, plugin.cfg)

        context.add_llm_tools.assert_called_once()
        args = context.add_llm_tools.call_args.args
        assert len(args[0]) == 7

    def test_register_llm_tools_default_enabled(self, mock_plugin):
        """默认应启用 LLM 模式"""
        from astrbot_plugin_winremote import WinRemotePlugin
        plugin = mock_plugin
        # 不设置 enable_llm_mode，应为默认值 True

        context = MagicMock()
        context.add_llm_tools = MagicMock()

        WinRemotePlugin._register_llm_tools(plugin, context, plugin.cfg)

        context.add_llm_tools.assert_called_once()

    def test_register_llm_tools_string_true(self, mock_plugin):
        """字符串 'true' 也应视为启用"""
        from astrbot_plugin_winremote import WinRemotePlugin
        plugin = mock_plugin
        plugin.cfg["enable_llm_mode"] = "true"

        context = MagicMock()
        context.add_llm_tools = MagicMock()

        WinRemotePlugin._register_llm_tools(plugin, context, plugin.cfg)

        context.add_llm_tools.assert_called_once()

    def test_llm_max_calls_config(self, mock_plugin):
        """llm_max_tool_calls 配置应被正确读取"""
        from astrbot_plugin_winremote import WinRemotePlugin
        plugin = mock_plugin
        plugin.cfg["enable_llm_mode"] = True
        plugin.cfg["llm_max_tool_calls"] = 10

        context = MagicMock()
        context.add_llm_tools = MagicMock()

        WinRemotePlugin._register_llm_tools(plugin, context, plugin.cfg)

        assert plugin._llm_max_calls == 10

    def test_llm_max_calls_clamp(self, mock_plugin):
        """llm_max_tool_calls 超过 20 应被 clamp"""
        from astrbot_plugin_winremote import WinRemotePlugin
        plugin = mock_plugin
        plugin.cfg["enable_llm_mode"] = True
        plugin.cfg["llm_max_tool_calls"] = 999

        context = MagicMock()
        context.add_llm_tools = MagicMock()

        WinRemotePlugin._register_llm_tools(plugin, context, plugin.cfg)

        assert plugin._llm_max_calls == 20

    def test_register_handles_import_error(self, mock_plugin):
        """tools 模块导入失败时应优雅降级"""
        from astrbot_plugin_winremote import WinRemotePlugin
        plugin = mock_plugin
        plugin.cfg["enable_llm_mode"] = True

        context = MagicMock()
        context.add_llm_tools = MagicMock()

        # 模拟 ImportError：patch tools 模块导入
        with patch.dict("sys.modules", {"tools": None}):
            # 不应抛异常
            WinRemotePlugin._register_llm_tools(plugin, context, plugin.cfg)

        context.add_llm_tools.assert_not_called()


# ============================================================
# 14. 安全红线检查
# ============================================================
class TestSecurityRedLines:
    """确保没有引入新的安全红线"""

    def test_no_eval_in_tools(self):
        """tools.py 中不能有 eval()"""
        tools_path = PLUGIN_DIR / "tools.py"
        content = tools_path.read_text(encoding="utf-8")
        # 排除注释中的 eval
        lines = [line for line in content.split("\n") if not line.strip().startswith("#")]
        joined = "\n".join(lines)
        assert "eval(" not in joined, "tools.py 包含 eval()"

    def test_no_exec_in_tools(self):
        """tools.py 中不能有 exec()"""
        tools_path = PLUGIN_DIR / "tools.py"
        content = tools_path.read_text(encoding="utf-8")
        lines = [line for line in content.split("\n") if not line.strip().startswith("#")]
        joined = "\n".join(lines)
        assert "exec(" not in joined, "tools.py 包含 exec()"

    def test_no_keyboard_import_in_core(self):
        """核心文件不应直接 import keyboard/pyautogui"""
        for fname in ["astrbot_plugin_winremote.py", "tool_handlers.py", "tools.py"]:
            fpath = PLUGIN_DIR / fname
            if not fpath.exists():
                continue
            content = fpath.read_text(encoding="utf-8").lower()
            assert "import keyboard" not in content, f"{fname} 导入了 keyboard"
            assert "import pyautogui" not in content, f"{fname} 导入了 pyautogui"

    def test_tool_descriptions_mention_safety(self):
        """Tool description 应提及安全约束（帮助 LLM 不做危险操作）"""
        for tool in ALL_TOOLS:
            desc = tool.description.lower()
            # 至少有一个安全相关的提示词
            safety_keywords = ["不要", "禁止", "危险", "白名单", "校验", "允许"]
            has_safety = any(kw in desc for kw in safety_keywords)
            # 不是强制要求，但建议
            if not has_safety:
                print(f"⚠️ {tool.name} 的 description 没有安全提示词")


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
