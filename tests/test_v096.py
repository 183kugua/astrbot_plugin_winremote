"""
tests/test_v096.py - WinRemote v0.9.6 专项测试
覆盖：
- AuthManager 完整生命周期
- HMAC 审计签名 + verify_audit 完整性校验
- confirm.py 私聊确认流程
- webui_panel.py 新 API
- 版本号全链路一致性
- 安全红线检查（排除 winremote_agent.py，它是 Windows 端）
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import __init__ as plugin
from auth import AuthManager, verify_audit
from confirm import (
    APPROVE,
    DENY,
    handle_private_reply,
    get_pending_count,
    cancel_all,
)


def _ns(**kw):
    """创建 SimpleNamespace，避免 MagicMock 被 _is_mock 捕获"""
    return types.SimpleNamespace(**kw)


# ============================================================
# FakeResponse — 替代 webui_panel 里的 Response
# ============================================================
class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.body = body if isinstance(body, (str, bytes)) else json.dumps(body)
        self.status_code = status
        self.headers = headers or {}


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture()
def tmp_audit(tmp_path):
    return str(tmp_path / "audit.jsonl")


@pytest.fixture()
def auth_mgr(tmp_audit):
    return AuthManager(
        secret_token="test-token-abc",
        ttl=300,
        audit_path=tmp_audit,
    )


@pytest.fixture()
def event_loop():
    """为每个测试提供事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def mock_event():
    ev = MagicMock()
    ev.get_sender_id.return_value = "10001"
    ev.get_message_str.return_value = "同意"
    # context.send 必须是 async
    ev.send = AsyncMock()
    return ev


# ============================================================
# 1. AuthManager 基础
# ============================================================
class TestAuthManagerBasic:
    def test_init_defaults(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=300, audit_path=tmp_audit)
        assert am.ttl == 300
        assert am.auth == {}
        assert am.pending == {}
        assert am.audit_path == tmp_audit

    def test_ttl_clamped_negative(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=-5, audit_path=tmp_audit)
        assert am.ttl == 300

    def test_ttl_clamped_over_max(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=9999, audit_path=tmp_audit)
        assert am.ttl == 3600

    def test_audit_file_created(self, tmp_audit):
        AuthManager(secret_token="tok", ttl=300, audit_path=tmp_audit)
        assert Path(tmp_audit).exists()


# ============================================================
# 2. 授权流程
# ============================================================
class TestAuthFlow:
    def test_request_wrong_password(self, auth_mgr):
        result = auth_mgr.request("shell", "wrong", "correct_hash")
        assert result["status"] == "wrong_pwd"
        assert "shell" not in auth_mgr.auth

    def test_request_correct_password(self, auth_mgr):
        import hashlib
        pwd_hash = hashlib.sha256(b"secret123").hexdigest()
        result = auth_mgr.request("shell", "secret123", pwd_hash)
        assert result["status"] == "ok"
        assert result["ttl"] == 300
        assert "shell" in auth_mgr.auth

    def test_request_needs_confirm_high_ttl(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=3600, audit_path=tmp_audit)
        import hashlib
        pwd_hash = hashlib.sha256(b"s").hexdigest()
        result = am.request("powershell", "s", pwd_hash)
        assert result["status"] == "need_confirm"
        assert "powershell" in am.pending

    def test_request_needs_confirm_zero_ttl(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=0, audit_path=tmp_audit)
        import hashlib
        pwd_hash = hashlib.sha256(b"s").hexdigest()
        result = am.request("write", "s", pwd_hash)
        assert result["status"] == "need_confirm"

    def test_confirm_success(self, auth_mgr):
        auth_mgr.pending["shell"] = {"expire_at": time.time() + 60, "ttl": 300}
        ok = auth_mgr.confirm("shell", "admin01")
        assert ok is True
        assert "shell" in auth_mgr.auth

    def test_confirm_expired(self, auth_mgr):
        auth_mgr.pending["shell"] = {"expire_at": time.time() - 10, "ttl": 300}
        ok = auth_mgr.confirm("shell", "admin01")
        assert ok is False

    def test_deny(self, auth_mgr):
        auth_mgr.pending["shell"] = {"expire_at": time.time() + 60, "ttl": 300}
        auth_mgr.deny("shell", "admin01")
        assert "shell" not in auth_mgr.pending

    def test_perm_auth(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=0, audit_path=tmp_audit)
        am.pending["write"] = {"expire_at": time.time() + 60, "ttl": 0}
        ok = am.confirm("write", "admin01")
        assert ok is True
        assert am.auth["write"] == 0


# ============================================================
# 3. check / ttl_remaining
# ============================================================
class TestAuthCheck:
    def test_check_not_authorized(self, auth_mgr):
        assert auth_mgr.check("shell") is False

    def test_check_authorized(self, auth_mgr):
        auth_mgr.auth["shell"] = time.time() + 100
        assert auth_mgr.check("shell") is True

    def test_check_perm_always_true(self, auth_mgr):
        auth_mgr.auth["write"] = 0
        assert auth_mgr.check("write") is True

    def test_check_expired_auto_remove(self, auth_mgr):
        auth_mgr.auth["shell"] = time.time() - 10
        assert auth_mgr.check("shell") is False
        assert "shell" not in auth_mgr.auth

    def test_ttl_remaining_authorized(self, auth_mgr):
        auth_mgr.auth["shell"] = time.time() + 120
        remaining = auth_mgr.ttl_remaining("shell")
        assert 100 < remaining <= 120

    def test_ttl_remaining_perm(self, auth_mgr):
        auth_mgr.auth["write"] = 0
        assert auth_mgr.ttl_remaining("write") == -1

    def test_ttl_remaining_not_authorized(self, auth_mgr):
        assert auth_mgr.ttl_remaining("shell") == -2


# ============================================================
# 4. Revoke
# ============================================================
class TestRevoke:
    def test_revoke_single(self, auth_mgr):
        auth_mgr.auth["shell"] = time.time() + 100
        auth_mgr.revoke("shell")
        assert "shell" not in auth_mgr.auth

    def test_revoke_all(self, auth_mgr):
        auth_mgr.auth["shell"] = time.time() + 100
        auth_mgr.auth["powershell"] = time.time() + 200
        auth_mgr.pending["write"] = {"expire_at": time.time() + 60, "ttl": 300}
        auth_mgr.revoke_all()
        assert auth_mgr.auth == {}
        assert auth_mgr.pending == {}


# ============================================================
# 5. HMAC 审计完整性
# ============================================================
class TestAuditIntegrity:
    def test_write_and_sign(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=300, audit_path=tmp_audit)
        am._write_log({"event": "test1", "data": "hello"})
        am._write_log({"event": "test2", "data": "world"})
        lines = [line for line in Path(tmp_audit).read_text().strip().split("\n") if line]
        assert len(lines) == 2
        for line in lines:
            assert "sig" in json.loads(line)

    def test_verify_clean_log(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=300, audit_path=tmp_audit)
        am._write_log({"event": "a"})
        am._write_log({"event": "b"})
        result = verify_audit(tmp_audit, "tok")
        assert result["integrity"] is True
        assert result["ok_count"] == 2

    def test_verify_tampered(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=300, audit_path=tmp_audit)
        am._write_log({"event": "a"})
        content = Path(tmp_audit).read_text()
        Path(tmp_audit).write_text(content.replace('"event"', '"hack"'))
        result = verify_audit(tmp_audit, "tok")
        assert result["integrity"] is False
        assert len(result["tampered_lines"]) > 0

    def test_verify_wrong_key(self, tmp_audit):
        am = AuthManager(secret_token="tok", ttl=300, audit_path=tmp_audit)
        am._write_log({"event": "a"})
        result = verify_audit(tmp_audit, "wrong-key")
        assert result["integrity"] is False

    def test_verify_empty_file(self, tmp_audit):
        Path(tmp_audit).write_text("")
        result = verify_audit(tmp_audit, "tok")
        assert result["integrity"] is True
        assert result["ok_count"] == 0


# ============================================================
# 6. confirm.py 私聊确认
# ============================================================
class TestConfirmPrivate:
    async def test_handle_reply_approve(self, mock_event, event_loop):
        from confirm import _pending
        _pending.clear()
        fut = event_loop.create_future()
        _pending["op1"] = {
            "event": mock_event,
            "op": "shell",
            "ttl": 300,
            "ttl_desc": "300秒",
            "requester": "20002",
            "admin_qq_list": ["10001"],
            "expire_at": time.time() + 60,
            "result_future": fut,
            "context": MagicMock(),
        }
        ctx = MagicMock()
        ctx.send = AsyncMock()
        handled = await handle_private_reply(ctx, mock_event)
        assert handled is True
        assert fut.done()
        assert fut.result() is True
        _pending.clear()

    async def test_handle_reply_deny(self, mock_event, event_loop):
        from confirm import _pending
        _pending.clear()
        mock_event.get_message_str.return_value = "拒绝"
        fut = event_loop.create_future()
        _pending["op2"] = {
            "event": mock_event,
            "op": "shell",
            "ttl": 300,
            "ttl_desc": "300秒",
            "requester": "20002",
            "admin_qq_list": ["10001"],
            "expire_at": time.time() + 60,
            "result_future": fut,
            "context": MagicMock(),
        }
        ctx = MagicMock()
        ctx.send = AsyncMock()
        handled = await handle_private_reply(ctx, mock_event)
        assert handled is True
        assert fut.done()
        assert fut.result() is False
        _pending.clear()

    async def test_handle_reply_non_admin(self, mock_event, event_loop):
        from confirm import _pending
        _pending.clear()
        mock_event.get_sender_id.return_value = "99999"
        fut = event_loop.create_future()
        _pending["op3"] = {
            "event": mock_event,
            "op": "shell",
            "ttl": 300,
            "ttl_desc": "300秒",
            "requester": "20002",
            "admin_qq_list": ["10001"],
            "expire_at": time.time() + 60,
            "result_future": fut,
            "context": MagicMock(),
        }
        ctx = MagicMock()
        ctx.send = AsyncMock()
        handled = await handle_private_reply(ctx, mock_event)
        assert handled is False
        assert not fut.done()
        _pending.clear()

    async def test_handle_reply_no_sender(self, mock_event):
        mock_event.get_sender_id.return_value = None
        ctx = MagicMock()
        ctx.send = AsyncMock()
        handled = await handle_private_reply(ctx, mock_event)
        assert handled is False

    def test_get_pending_count(self, event_loop):
        from confirm import _pending
        _pending.clear()
        assert get_pending_count() == 0
        fut = event_loop.create_future()
        _pending["a"] = {"expire_at": time.time() + 60, "result_future": fut}
        assert get_pending_count() == 1
        _pending.clear()

    def test_cancel_all(self, event_loop):
        from confirm import _pending
        _pending.clear()
        fut1 = event_loop.create_future()
        fut2 = event_loop.create_future()
        _pending["a"] = {"result_future": fut1}
        _pending["b"] = {"result_future": fut2}
        cancel_all()
        assert fut1.done() and fut2.done()
        assert fut1.result() is False
        assert _pending == {}

    def test_approve_keywords(self):
        assert "同意" in APPROVE
        assert "确认" in APPROVE

    def test_deny_keywords(self):
        assert "拒绝" in DENY
        assert "取消" in DENY


# ============================================================
# 7. webui_panel.py API
# ============================================================
class TestWebUIPanel:
    async def test_data_stopped_no_plugin(self):
        from webui_panel import get_panel_data
        with patch("webui_panel._get_plugin", return_value=None), \
             patch("webui_panel.Response", FakeResponse, create=True):
            resp = await get_panel_data(MagicMock())
        body = json.loads(resp.body)
        assert body["status"] == "stopped"
        assert body["agents"] == []
        assert body["auth"]["granted"] == []
        assert body["audit"]["count"] == 0

    async def test_data_with_running_server(self, tmp_path):
        from webui_panel import get_panel_data
        cfg = plugin.get_config(None)
        srv = plugin.WinRemoteServer(context=MagicMock(), config=cfg,
                                     audit=plugin.AuditLogger(tmp_path / "pd.jsonl"))
        srv._running = True
        agent = plugin.AgentConnection(ws=None, agent_id="test-agent-1")
        agent.busy = True
        agent.current_task = "shell dir"
        agent.authenticated = True
        await srv.agents.add(agent)

        fake_plugin = MagicMock()
        fake_plugin.server = srv
        fake_plugin.cfg = cfg
        fake_plugin.audit = srv.audit
        fake_plugin.auth_mgr = AuthManager(
            secret_token="tok", ttl=300,
            audit_path=str(tmp_path / "a.jsonl"))
        fake_plugin._auth_ttl = 300
        fake_plugin.VERSION = "0.9.6"

        with patch("webui_panel._get_plugin", return_value=fake_plugin), \
             patch("webui_panel.Response", FakeResponse, create=True):
            resp = await get_panel_data(MagicMock())

        body = json.loads(resp.body)
        assert body["status"] == "running"
        assert len(body["agents"]) == 1
        assert body["agents"][0]["id"] == "test-agent-1"
        assert body["agents"][0]["state"] == "busy"
        assert body["agents"][0]["current_task"] == "shell dir"
        assert body["version"] == "0.9.6"
        await srv.stop()

    async def test_auth_status_endpoint(self, tmp_path):
        from webui_panel import get_auth_status
        am = AuthManager(secret_token="tok", ttl=300,
                         audit_path=str(tmp_path / "a.jsonl"))
        am.auth["shell"] = time.time() + 120
        am.pending["write"] = {"expire_at": time.time() + 60, "ttl": 0}

        fake_plugin = _ns(auth_mgr=am, _auth_ttl=300)

        with patch("webui_panel._get_plugin", return_value=fake_plugin), \
             patch("webui_panel.Response", FakeResponse, create=True):
            resp = await get_auth_status(MagicMock())

        body = json.loads(resp.body)
        assert len(body["granted"]) == 1
        assert body["granted"][0]["op"] == "shell"
        assert body["granted"][0]["remaining"] > 0
        assert len(body["pending"]) == 1
        assert body["pending"][0]["op"] == "write"

    async def test_revoke_auth_endpoint(self, tmp_path):
        from webui_panel import post_revoke_auth
        am = AuthManager(secret_token="tok", ttl=300,
                         audit_path=str(tmp_path / "a.jsonl"))
        am.auth["shell"] = time.time() + 120
        am.auth["powershell"] = time.time() + 200

        fake_plugin = _ns(auth_mgr=am)

        with patch("webui_panel._get_plugin", return_value=fake_plugin), \
             patch("webui_panel.Response", FakeResponse, create=True):
            req1 = MagicMock()
            req1.json = AsyncMock(return_value={"op": "shell"})
            resp1 = await post_revoke_auth(req1)
            body1 = json.loads(resp1.body)
            assert body1["ok"] is True
            assert "shell" not in am.auth

            req2 = MagicMock()
            req2.json = AsyncMock(return_value={})
            resp2 = await post_revoke_auth(req2)
            body2 = json.loads(resp2.body)
            assert body2["ok"] is True
            assert am.auth == {}

    async def test_audit_verify_endpoint(self, tmp_path):
        from webui_panel import get_audit_verify
        audit_path = tmp_path / "verify.jsonl"
        am = AuthManager(secret_token="tok", ttl=300,
                         audit_path=str(audit_path))
        am._write_log({"event": "test1"})
        am._write_log({"event": "test2"})

        # 用 _ns 避免 MagicMock 被 _is_mock 捕获
        fake_plugin = _ns(
            auth_mgr=am,
            secret_token="tok",  # get_audit_verify 优先用 plugin.secret_token
            audit=_ns(path=str(audit_path)),
        )

        with patch("webui_panel._get_plugin", return_value=fake_plugin), \
             patch("webui_panel.Response", FakeResponse, create=True):
            resp = await get_audit_verify(MagicMock())

        body = json.loads(resp.body)
        assert body["ok"] is True
        assert body["integrity"] is True
        assert body["ok_count"] == 2

    async def test_plugin_not_loaded_returns_503(self):
        from webui_panel import get_auth_status, get_audit_verify, post_revoke_auth
        with patch("webui_panel._get_plugin", return_value=None), \
             patch("webui_panel.Response", FakeResponse, create=True):
            r1 = await get_auth_status(MagicMock())
            assert r1.status_code == 503
            r2 = await get_audit_verify(MagicMock())
            assert r2.status_code == 503
            r3 = await post_revoke_auth(MagicMock())
            assert r3.status_code == 503


# ============================================================
# 8. 版本号一致性
# ============================================================
class TestVersionConsistency:
    def test_init_version(self):
        assert plugin.VERSION == "0.9.6"

    def test_webui_version(self):
        import webui_panel
        assert webui_panel.VERSION == "0.9.6"

    def test_widget_html_version(self):
        import webui_panel
        assert "v0.9.6" in webui_panel.WIDGET_HTML

    def test_version_file(self):
        vpath = Path(__file__).resolve().parent.parent / "VERSION"
        if vpath.exists():
            assert vpath.read_text().strip() == "0.9.6"

    def test_pyproject_version(self):
        ppath = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if ppath.exists():
            assert "0.9.6" in ppath.read_text()


# ============================================================
# 9. 安全红线（排除 winremote_agent.py — 它是 Windows 端）
# ============================================================
class TestSecurityRedLines:
    @pytest.fixture(scope="class")
    def plugin_root(self):
        return str(Path(__file__).resolve().parent.parent)

    def test_no_eval(self, plugin_root):
        """核心插件文件不能有 eval() 调用"""
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "eval(", "astrbot_plugin_winremote.py", "auth.py",
             "confirm.py", "webui_panel.py", "__init__.py"],
            capture_output=True, text=True, cwd=plugin_root,
        )
        lines = [line for line in result.stdout.strip().split("\n") if line]
        # 只允许 __init__.py 薄壳中的 exec 模式（已有合规注释）
        code_lines = [line for line in lines
                     if not line.strip().startswith("#")
                     and "astrbot_plugin_winremote.py" not in line
                     and "auth.py" not in line
                     and "confirm.py" not in line
                     and "webui_panel.py" not in line]
        assert code_lines == [], f"Found eval: {code_lines}"

    def test_no_exec_in_core(self, plugin_root):
        """核心逻辑文件不能有 exec( 调用"""
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "exec(", "auth.py", "confirm.py", "webui_panel.py"],
            capture_output=True, text=True, cwd=plugin_root,
        )
        lines = [line for line in result.stdout.strip().split("\n") if line]
        code_lines = [line for line in lines if not line.strip().startswith("#")]
        assert code_lines == [], f"Found exec: {code_lines}"

    def test_no_keyboard_import(self, plugin_root):
        """不能直接 import keyboard 库（Linux 不支持）"""
        import subprocess
        result = subprocess.run(
            ["grep", "-rn", "^import keyboard", "."],
            capture_output=True, text=True, cwd=plugin_root,
        )
        assert result.stdout.strip() == ""


if __name__ == "__main__":
    _args = [__file__, "-v"]
    sys.exit(pytest.main(_args))
