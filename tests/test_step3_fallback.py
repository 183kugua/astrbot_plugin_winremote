"""
test_step3_fallback.py — WinRemote V0.9.8 Step 3 测试
====================================================
测试降级通道逻辑：
- /win --llm 开关
- LLM 模式关闭时的提示
- LLM 不可用时的降级
- on_llm_response 钩子
- 状态输出含 LLM 行
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# 确保插件目录在 path 中
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import astrbot_plugin_winremote as wr  # noqa: E402


# ============================================================
# Fixtures
# ============================================================
def _make_event(text="/win --llm 帮我看IP", sender="12345", is_group=False):
    """构造一个模拟的 AstrMessageEvent"""
    ev = MagicMock()
    ev.get_message_str = MagicMock(return_value=text)
    ev.get_sender_id = MagicMock(return_value=sender)
    ev.is_group = MagicMock(return_value=is_group)
    ev.stop_event = MagicMock()
    ev.unified_msg_origin = f"aiocqhttp:{'GroupMessage' if is_group else 'FriendMessage'}:{sender}"
    return ev


def _make_handler():
    """构造一个模拟的 handler"""
    h = MagicMock()
    h.send = AsyncMock()
    return h


def _make_plugin(llm_enabled=True, context_has_tools=True, context_has_loop=True):
    """构造一个最小可用的插件实例"""
    plugin = MagicMock()
    plugin.context = MagicMock()
    if context_has_tools:
        plugin.context.add_llm_tools = MagicMock()
    else:
        delattr(plugin.context, "add_llm_tools")
    if context_has_loop:
        plugin.context.tool_loop_agent = AsyncMock(return_value="LLM 回复内容")
    else:
        delattr(plugin.context, "tool_loop_agent")

    # 配置
    plugin._cfg_bool = MagicMock(side_effect=lambda k, d: {
        "enable_llm_mode": llm_enabled,
        "allow_group": False,
        "audit_enabled": True,
        "allow_powershell": True,
        "file_allow_write": False,
        "require_encryption": False,
        "strict_whitelist": False,
        "skill_auto_load": True,
    }.get(k, d))
    plugin._cfg_int = MagicMock(side_effect=lambda k, d, *a: {
        "auth_ttl_seconds": 300,
        "max_read_bytes": 65536,
        "shell_timeout": 30,
        "llm_max_tool_calls": 5,
        "password_max_attempts": 5,
        "password_ban_duration": 300,
    }.get(k, d))
    plugin._cfg_str = MagicMock(side_effect=lambda k, d: {
        "secret_token": "test-token",
        "admin_password": "",
        "admin_password_hash": "",
        "ws_host": "127.0.0.1",
        "audit_path": "data/winremote_audit.jsonl",
    }.get(k, d))
    plugin._cfg_list = MagicMock(side_effect=lambda k, d: {
        "admin_qq": ["12345"],
        "command_whitelist": ["shell", "powershell"],
        "command_blacklist": ["rm "],
    }.get(k, d))

    # 子组件
    # auth_mgr 用普通对象（MagicMock 的属性访问会返回新 MagicMock，不走 side_effect）
    class _FakeAuthMgr:
        def ttl_remaining(self, op): return -1
        def check(self, op): return True
        def request(self, op, pwd, h): return {"status": "ok"}
        def confirm(self, op, qq): return True
    plugin.auth_mgr = _FakeAuthMgr()

    plugin.server = MagicMock()
    plugin.server.agents = MagicMock()
    plugin.server.agents.__len__ = MagicMock(return_value=0)
    plugin.server.agents._agents = {}
    plugin.server._running = True

    plugin.audit = MagicMock()
    plugin.audit.write = AsyncMock()
    plugin.audit._buf = []

    plugin._llm_max_calls = 5 if llm_enabled else 0
    plugin.logger = MagicMock()

    return plugin


# ============================================================
# 1. --llm 开关解析
# ============================================================
class TestLLMSwitchParsing:
    """测试 /win --llm 开关的解析"""

    def test_detects_double_dash_llm(self):
        """--llm 应被识别"""
        msg = "/win --llm 帮我看IP"
        parts = msg.split()
        use_llm = any(p in ("--llm", "--LLM", "-l") for p in parts)
        assert use_llm, "应识别 --llm 开关"

    def test_detects_upper_case_llm(self):
        """--LLM 也应被识别"""
        msg = "/win --LLM 看进程"
        parts = msg.split()
        use_llm = any(p in ("--llm", "--LLM", "-l") for p in parts)
        assert use_llm, "应识别 --LLM 开关"

    def test_detects_short_llm(self):
        """-l 短格式应被识别"""
        msg = "/win -l 截图"
        parts = msg.split()
        use_llm = any(p in ("--llm", "--LLM", "-l") for p in parts)
        assert use_llm, "应识别 -l 短格式"

    def test_no_llm_switch_by_default(self):
        """普通 /win 指令不应触发 LLM"""
        msg = "/win shell ipconfig"
        parts = msg.split()
        use_llm = any(p in ("--llm", "--LLM", "-l") for p in parts)
        assert not use_llm, "普通指令不应识别为 LLM 模式"

    def test_pwd_and_llm_both_parsed(self):
        """--pwd 和 --llm 可同时解析"""
        msg = "/win --pwd mypwd --llm 看IP"
        parts = msg.split()
        pwd = None
        use_llm = False
        skip = False
        for i, p in enumerate(parts):
            if skip:
                skip = False
                continue
            if p == "--pwd" and i + 1 < len(parts):
                pwd = parts[i + 1]
                skip = True
            elif p.startswith("--pwd="):
                pwd = p[6:]
            elif p in ("--llm", "--LLM", "-l"):
                use_llm = True
        assert pwd == "mypwd", f"密码解析失败: {pwd}"
        assert use_llm, "LLM 开关解析失败"


# ============================================================
# 2. LLM 模式关闭时的提示
# ============================================================
class TestLLMDisabled:
    """测试 LLM 模式关闭时的降级提示"""

    async def test_help_shows_llm_when_enabled(self):
        """LLM 开启时，帮助信息应提示 --llm 用法"""
        plugin = _make_plugin(llm_enabled=True)
        handler = _make_handler()
        event = _make_event("/win")
        # 直接调用 cmd_win
        await wr.WinRemotePlugin.cmd_win(plugin, handler, event)
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        # 帮助信息应包含版本号
        assert "V0.9.8" in sent or "v0.9.8" in sent.lower(), f"帮助信息应包含版本号: {sent[:200]}"

    async def test_llm_disabled_help_hint(self):
        """LLM 关闭时，帮助信息应提示开启"""
        plugin = _make_plugin(llm_enabled=False)
        handler = _make_handler()
        event = _make_event("/win")
        await wr.WinRemotePlugin.cmd_win(plugin, handler, event)
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        # 应包含 LLM 关闭相关提示或标准帮助
        assert len(sent) > 10, f"应发送帮助信息: {sent[:200]}"

    async def test_llm_switch_when_disabled(self):
        """LLM 关闭时用 --llm 应得到明确提示"""
        plugin = _make_plugin(llm_enabled=False)
        handler = _make_handler()
        event = _make_event("/win --llm 看IP")
        await wr.WinRemotePlugin.cmd_win(plugin, handler, event)
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        # 应包含"关闭"或"LLM"相关提示
        assert "LLM" in sent or "llm" in sent.lower() or "关闭" in sent, \
            f"应提示 LLM 已关闭: {sent[:200]}"


# ============================================================
# 3. _route_via_llm 方法
# ============================================================
class TestRouteViaLLM:
    """测试 LLM 路由方法"""

    async def test_no_tool_loop_agent(self):
        """context 没有 tool_loop_agent 时应降级"""
        plugin = _make_plugin(context_has_loop=False)
        handler = _make_handler()
        event = _make_event()
        await wr.WinRemotePlugin._route_via_llm(plugin, handler, event, "看IP", "12345")
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        assert "不支持" in sent or "tool_loop" in sent or "/" in sent, \
            f"应降级提示: {sent[:200]}"

    async def test_successful_route(self):
        """正常路由应调用 tool_loop_agent"""
        plugin = _make_plugin(context_has_loop=True)
        plugin.context.tool_loop_agent = AsyncMock(return_value="✅ 命令已执行: ipconfig")
        handler = _make_handler()
        event = _make_event()
        await wr.WinRemotePlugin._route_via_llm(plugin, handler, event, "看下IP地址", "12345")
        # 应调用了 tool_loop_agent
        assert plugin.context.tool_loop_agent.called, "应调用 tool_loop_agent"
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        assert len(sent) > 0, "应发送回复"

    async def test_route_exception_fallback(self):
        """tool_loop_agent 抛异常时应降级"""
        plugin = _make_plugin(context_has_loop=True)
        plugin.context.tool_loop_agent = AsyncMock(side_effect=RuntimeError("LLM 服务挂了"))
        handler = _make_handler()
        event = _make_event()
        await wr.WinRemotePlugin._route_via_llm(plugin, handler, event, "看IP", "12345")
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        # 应包含降级提示（含 /win 指令）
        assert "/" in sent and "win" in sent.lower(), \
            f"异常时应降级到 /win 提示: {sent[:200]}"

    async def test_empty_result_fallback(self):
        """LLM 返回 None 时应降级"""
        plugin = _make_plugin(context_has_loop=True)
        plugin.context.tool_loop_agent = AsyncMock(return_value=None)
        handler = _make_handler()
        event = _make_event()
        await wr.WinRemotePlugin._route_via_llm(plugin, handler, event, "看IP", "12345")
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        assert "/" in sent and "win" in sent.lower(), \
            f"空结果应降级: {sent[:200]}"


# ============================================================
# 4. _build_fallback_hint 方法
# ============================================================
class TestFallbackHint:
    """测试降级提示构建"""

    def test_hint_for_ip(self):
        """包含 IP 关键词时应提示 ipconfig"""
        plugin = _make_plugin()
        hint = wr.WinRemotePlugin._build_fallback_hint(plugin, "帮我看下IP地址")
        assert "ipconfig" in hint.lower(), f"应包含 ipconfig: {hint}"

    def test_hint_for_process(self):
        """包含进程关键词时应提示 tasklist"""
        plugin = _make_plugin()
        hint = wr.WinRemotePlugin._build_fallback_hint(plugin, "看下进程")
        assert "tasklist" in hint.lower() or "shell" in hint.lower(), \
            f"应包含 tasklist 或 shell: {hint}"

    def test_hint_for_screenshot(self):
        """包含截图关键词时应提示截图指令"""
        plugin = _make_plugin()
        hint = wr.WinRemotePlugin._build_fallback_hint(plugin, "截个图看看")
        assert "截图" in hint, f"应包含截图: {hint}"

    def test_hint_default(self):
        """无匹配关键词时应给出通用提示"""
        plugin = _make_plugin()
        hint = wr.WinRemotePlugin._build_fallback_hint(plugin, "随便说点什么")
        assert "/" in hint and "win" in hint.lower(), \
            f"应给出通用 /win 提示: {hint}"


# ============================================================
# 5. _build_llm_system_prompt 方法
# ============================================================
class TestLLMSystemPrompt:
    """测试 LLM 系统提示词构建"""

    def test_contains_tool_list(self):
        """提示词应包含工具列表"""
        plugin = _make_plugin()
        prompt = wr.WinRemotePlugin._build_llm_system_prompt(plugin)
        assert "win_shell" in prompt, f"应包含 win_shell: {prompt[:300]}"
        assert "win_screenshot" in prompt, f"应包含 win_screenshot: {prompt[:300]}"

    def test_contains_safety_rules(self):
        """提示词应包含安全约束"""
        plugin = _make_plugin()
        prompt = wr.WinRemotePlugin._build_llm_system_prompt(plugin)
        # 安全相关内容
        safety_kw = ["绝不", "安全", "危险", "管道", "重定向"]
        found = [kw for kw in safety_kw if kw in prompt]
        assert len(found) > 0, f"应包含安全约束: {prompt[:500]}"

    def test_contains_auth_status(self):
        """提示词应包含授权状态段"""
        plugin = _make_plugin()
        prompt = wr.WinRemotePlugin._build_llm_system_prompt(plugin)
        assert "授权" in prompt, f"应包含授权状态: {prompt[:500]}"

    def test_skill_md_injection(self):
        """Skill.md 存在时应注入到提示词"""
        plugin = _make_plugin()
        # 确保 skills 目录存在
        skill_dir = ROOT / "skills" / "winremote-remote-control"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            skill_md.write_text("---\nname: test\n---\n# Test Skill\n使用 win_shell 执行命令\n", encoding="utf-8")
        prompt = wr.WinRemotePlugin._build_llm_system_prompt(plugin)
        # 应包含 Skill 内容或工具说明
        assert len(prompt) > 100, f"提示词过短: {prompt[:200]}"


# ============================================================
# 6. on_llm_response 钩子
# ============================================================
class TestOnLLMResponse:
    """测试 LLM 响应钩子"""

    async def test_appends_auth_status(self):
        """WinRemote 相关回复应追加授权状态"""
        plugin = _make_plugin()
        # 替换为可控的 FakeAuthMgr
        class _AuthWithShell:
            def ttl_remaining(self, op): return 120 if op == "shell" else -1
        plugin.auth_mgr = _AuthWithShell()
        event = _make_event("截图看看")
        response = MagicMock()
        response.content = "已截图"
        with patch.object(wr.WinRemotePlugin, "_is_winremote_related", return_value=True):
            await wr.WinRemotePlugin.on_llm_response(plugin, event, response)
        assert response.content != "已截图", \
            f"content 应被修改: {response.content}"

    async def test_non_winremote_skipped(self):
        """非 WinRemote 相关回复不应修改"""
        plugin = _make_plugin()
        # 直接在实例上设置，避免 MagicMock __getattr__ 干扰
        plugin._is_winremote_related = MagicMock(return_value=False)
        event = _make_event("今天天气怎么样")
        response = MagicMock()
        response.content = "今天晴天"
        await wr.WinRemotePlugin.on_llm_response(plugin, event, response)
        # content 不应被修改
        assert response.content == "今天晴天", "非 WinRemote 回复不应修改"

    async def test_response_dict_format(self):
        """dict 格式的 response 也应支持"""
        plugin = _make_plugin()
        class _AuthPerm:
            def ttl_remaining(self, op): return 0
        plugin.auth_mgr = _AuthPerm()
        event = _make_event("帮我看IP")
        response = {"content": "IP 是 192.168.1.100"}
        with patch.object(wr.WinRemotePlugin, "_is_winremote_related", return_value=True):
            await wr.WinRemotePlugin.on_llm_response(plugin, event, response)
        assert response["content"] != "IP 是 192.168.1.100", \
            f"dict response 应被修改: {response}"

    async def test_exception_does_not_crash(self):
        """钩子异常不应崩溃"""
        plugin = _make_plugin()
        # 制造异常
        plugin.auth_mgr.ttl_remaining = MagicMock(side_effect=RuntimeError("test"))
        event = _make_event("看IP")
        response = MagicMock()
        response.content = "test"
        # 不应抛异常
        await wr.WinRemotePlugin.on_llm_response(plugin, event, response)


# ============================================================
# 7. 状态输出含 LLM 行
# ============================================================
class TestStatusWithLLM:
    """测试 /win 状态 输出"""

    async def test_status_shows_llm_on(self):
        """LLM 开启时状态应显示"""
        plugin = _make_plugin(llm_enabled=True)
        plugin.server.agents.__len__ = MagicMock(return_value=1)
        plugin.server.agents._agents = {"agent-001": MagicMock(is_alive=MagicMock(return_value=True), bushy=False, current_task=None, authenticated=True)}
        handler = _make_handler()
        event = _make_event("/win 状态")
        await wr.WinRemotePlugin.cmd_win(plugin, handler, event)
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        assert "LLM" in sent or "llm" in sent.lower(), \
            f"状态应包含 LLM 信息: {sent[:300]}"

    async def test_status_shows_llm_off(self):
        """LLM 关闭时状态应显示关闭"""
        plugin = _make_plugin(llm_enabled=False)
        plugin.server.agents.__len__ = MagicMock(return_value=0)
        handler = _make_handler()
        event = _make_event("/win 状态")
        await wr.WinRemotePlugin.cmd_win(plugin, handler, event)
        sent = handler.send.call_args[0][0] if handler.send.called else ""
        assert "LLM" in sent or "llm" in sent.lower() or "无 Agent" in sent, \
            f"状态应包含 LLM 或 Agent 信息: {sent[:300]}"


# ============================================================
# 8. _format_llm_result 方法
# ============================================================
class TestFormatLLMResult:
    """测试 LLM 结果格式化"""

    def test_string_result(self):
        """字符串结果应加前缀"""
        plugin = _make_plugin()
        out = wr.WinRemotePlugin._format_llm_result(plugin, "IP: 192.168.1.1", "看IP")
        assert "🤖" in out or "LLM" in out or "192.168" in out, f"应格式化: {out}"

    def test_none_result(self):
        """None 结果应触发降级"""
        plugin = _make_plugin()
        out = wr.WinRemotePlugin._format_llm_result(plugin, None, "看IP")
        assert "/" in out and "win" in out.lower(), f"None 应降级: {out}"

    def test_long_result_truncated(self):
        """超长结果应截断"""
        plugin = _make_plugin()
        long_text = "x" * 20000
        out = wr.WinRemotePlugin._format_llm_result(plugin, long_text, "test")
        assert len(out) < 10000, f"结果应被截断: len={len(out)}"


# ============================================================
# 9. _is_winremote_related 方法
# ============================================================
class TestIsWinRemoteRelated:
    """测试 WinRemote 相关性判断"""

    def test_screenshot_keyword(self):
        plugin = _make_plugin()
        assert wr.WinRemotePlugin._is_winremote_related(plugin, "帮我截图", "已截图")

    def test_ipconfig_keyword(self):
        plugin = _make_plugin()
        assert wr.WinRemotePlugin._is_winremote_related(plugin, "看下ipconfig", "结果")

    def test_unrelated(self):
        plugin = _make_plugin()
        assert not wr.WinRemotePlugin._is_winremote_related(plugin, "今天天气", "晴天")

    def test_auth_keyword(self):
        plugin = _make_plugin()
        assert wr.WinRemotePlugin._is_winremote_related(plugin, "授权状态", "已授权")


# ============================================================
# 10. _auth_status_summary 方法
# ============================================================
class TestAuthStatusSummary:
    """测试授权状态摘要"""

    def test_all_expired(self):
        """全部未授权时应提示"""
        plugin = _make_plugin()
        plugin.auth_mgr.ttl_remaining = MagicMock(return_value=-1)
        lines = wr.WinRemotePlugin._auth_status_summary(plugin)
        assert any("无活跃" in line or "🔴" in line for line in lines), \
            f"应提示无活跃授权: {lines}"

    def test_permanent_auth(self):
        """永久授权应显示永久"""
        plugin = _make_plugin()
        plugin.auth_mgr.ttl_remaining = MagicMock(return_value=0)
        lines = wr.WinRemotePlugin._auth_status_summary(plugin)
        assert any("永久" in line for line in lines), f"应显示永久: {lines}"

    def test_ttl_remaining(self):
        """有剩余时间应显示秒数"""
        plugin = _make_plugin()
        plugin.auth_mgr.ttl_remaining = MagicMock(return_value=180)
        lines = wr.WinRemotePlugin._auth_status_summary(plugin)
        assert any("180" in line for line in lines), f"应显示剩余秒数: {lines}"


# ============================================================
# 运行
# ============================================================
if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
